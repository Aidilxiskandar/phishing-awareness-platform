"""Right to erasure: a person's PII is anonymised everywhere, aggregates survive."""
from sqlmodel import select

from app.maintenance import erase_by_email, main
from app.models import (
    AuditLog,
    Campaign,
    Event,
    QuizResult,
    StaffGroup,
    StaffGroupLink,
    Target,
    TrainingModule,
    User,
)
from app.services.erasure import erase_user, placeholder_email

EMAIL = "victim@example.com"
UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"


def _arrange(client, session_factory) -> tuple[int, str]:
    """A consenting user in a group, targeted by a campaign, who opened + clicked
    and took a quiz. Returns (user_id, original token)."""
    client.post("/users", data={"email": EMAIL, "name": "Vic Tim",
                                "department": "Finance", "consented": "on"})
    client.post("/campaigns", data={"name": "C", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    client.post("/groups", data={"name": "G"})
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
        cid = s.exec(select(Campaign.id)).first()
        gid = s.exec(select(StaffGroup.id)).first()
    client.post("/users/assign", data={"group_id": gid, "user_ids": uid})
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    with session_factory() as s:
        token = s.exec(select(Target.token)).first()
        module = s.exec(select(TrainingModule)).first()
        s.add(QuizResult(module_id=module.id, token=token, user_id=uid, score=2, total=3))
        s.commit()
    client.get(f"/t/open/{token}.png", headers={"user-agent": UA})
    client.get(f"/t/click/{token}", headers={"user-agent": UA})
    return uid, token


def test_erase_route_anonymises_everything(client, session_factory):
    uid, token = _arrange(client, session_factory)

    r = client.post(f"/users/{uid}/erase", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/users?notice=erased"

    with session_factory() as s:
        user = s.get(User, uid)
        assert user.email == placeholder_email(uid)
        assert (user.name, user.department, user.consented) == ("", "", False)
        assert user.erased_at is not None

        target = s.exec(select(Target)).one()
        assert target.email == placeholder_email(uid) and target.name == ""
        assert target.token != token and not target.consented

        events = s.exec(select(Event)).all()
        assert len(events) >= 2, "behavioural events are kept for aggregates"
        assert all(e.ip == "" and e.user_agent == "" for e in events)

        quiz = s.exec(select(QuizResult)).one()
        assert quiz.user_id is None and quiz.token == ""

        assert s.exec(select(StaffGroupLink)).all() == []

        audits = s.exec(select(AuditLog)).all()
        assert not any(EMAIL in a.detail for a in audits), "email scrubbed from audit log"
        assert any(a.action == "user.erase" for a in audits)


def test_old_tracking_links_stop_working(client, anon, session_factory):
    uid, token = _arrange(client, session_factory)
    client.post(f"/users/{uid}/erase")
    assert anon.get(f"/t/click/{token}").status_code == 404


def test_erased_user_hidden_from_lists_and_reports(client, session_factory):
    uid, _ = _arrange(client, session_factory)
    client.post(f"/users/{uid}/erase")

    users_page = client.get("/users")
    assert users_page.status_code == 200
    assert "Personal data erased" not in users_page.text  # notice only via redirect
    assert placeholder_email(uid) not in users_page.text
    assert "Personal data erased" in client.get("/users?notice=erased").text

    # Evidence rows stay (as the anonymous placeholder); the real address is gone.
    reports = client.get("/reports").text
    assert EMAIL not in reports and "Vic Tim" not in reports
    assert EMAIL not in client.get("/reports/export.csv").text


def test_erased_user_cannot_be_retargeted(client, session_factory):
    uid, _ = _arrange(client, session_factory)
    client.post(f"/users/{uid}/erase")
    client.post("/campaigns", data={"name": "C2", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    with session_factory() as s:
        cid2 = s.exec(select(Campaign.id).where(Campaign.name == "C2")).one()
    client.post(f"/campaigns/{cid2}/targets", data={"user_ids": uid})
    with session_factory() as s:
        assert s.exec(select(Target).where(Target.campaign_id == cid2)).all() == []


def test_erase_unknown_user(client, session_factory):
    r = client.post("/users/9999/erase", follow_redirects=False)
    assert r.headers["location"] == "/users?error=not_found"
    with session_factory() as s:
        assert erase_user(s, 9999) is None


def test_erase_is_idempotent(client, session_factory):
    uid, _ = _arrange(client, session_factory)
    with session_factory() as s:
        first = erase_user(s, uid)
        erased_at = s.get(User, uid).erased_at
    with session_factory() as s:
        again = erase_user(s, uid)
        assert s.get(User, uid).erased_at == erased_at
    assert first["targets"] == again["targets"] == 1


def test_same_email_can_rejoin_as_new_person(client, session_factory):
    uid, _ = _arrange(client, session_factory)
    client.post(f"/users/{uid}/erase")
    client.post("/users", data={"email": EMAIL, "name": "Back Again"})
    with session_factory() as s:
        fresh = s.exec(select(User).where(User.email == EMAIL)).one()
        assert fresh.id != uid and fresh.erased_at is None and not fresh.consented


def test_erase_requires_auth(anon, client, session_factory):
    uid, _ = _arrange(client, session_factory)
    assert anon.post(f"/users/{uid}/erase", follow_redirects=False).status_code == 401


def test_cli_erase(client, session_factory, capsys):
    uid, _ = _arrange(client, session_factory)
    assert main(["erase", EMAIL]) == 0
    assert "Erased" in capsys.readouterr().out
    with session_factory() as s:
        assert s.get(User, uid).erased_at is not None
        assert any(a.actor == "cli" and a.action == "user.erase"
                   for a in s.exec(select(AuditLog)).all())
    assert erase_by_email("nobody@example.com") is None
    assert main(["erase", "nobody@example.com"]) == 1
    assert main(["erase"]) == 2
