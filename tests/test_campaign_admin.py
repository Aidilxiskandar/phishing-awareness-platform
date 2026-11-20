"""Campaign admin flows: email preview, group targeting, staff seeding, helpers."""
import pytest
from sqlmodel import select

from app import mailer
from app.config import Settings
from app.main import humandur
from app.models import Campaign, StaffGroup, Target, User


def _campaign(client, session_factory, name="C") -> int:
    client.post("/campaigns", data={"name": name, "subject": "Reset your password",
                                    "from_name": "IT", "from_email": "it@example.com"})
    with session_factory() as s:
        return s.exec(select(Campaign.id).where(Campaign.name == name)).one()


def _targeted(client, session_factory) -> tuple[int, int, str]:
    client.post("/users", data={"email": "p@example.com", "name": "Pat", "consented": "on"})
    cid = _campaign(client, session_factory)
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    with session_factory() as s:
        t = s.exec(select(Target)).one()
    return cid, t.id, t.token


def test_email_preview_and_raw_html(client, session_factory):
    cid, tid, _ = _targeted(client, session_factory)
    page = client.get(f"/campaigns/{cid}/preview/{tid}")
    assert page.status_code == 200 and "Reset your password" in page.text
    raw = client.get(f"/campaigns/{cid}/email/{tid}")
    assert raw.status_code == 200 and "<html" in raw.text.lower()


def test_preview_rejects_target_from_other_campaign(client, session_factory):
    _, tid, _ = _targeted(client, session_factory)
    other = _campaign(client, session_factory, "Other")
    assert client.get(f"/campaigns/{other}/preview/{tid}").status_code == 404
    assert client.get(f"/campaigns/{other}/email/{tid}").status_code == 404
    assert client.get("/campaigns/999/email/999").status_code == 404


def test_add_group_as_targets_skips_duplicates(client, session_factory):
    for i in range(3):
        client.post("/users", data={"email": f"g{i}@example.com", "consented": "on"})
    client.post("/groups", data={"name": "Finance"})
    with session_factory() as s:
        uids = s.exec(select(User.id)).all()
        gid = s.exec(select(StaffGroup.id)).one()
    client.post("/users/assign", data={"group_id": gid, "user_ids": uids})
    cid = _campaign(client, session_factory)
    client.post(f"/campaigns/{cid}/targets_group", data={"group_id": gid})
    client.post(f"/campaigns/{cid}/targets_group", data={"group_id": gid})  # again
    with session_factory() as s:
        targets = s.exec(select(Target).where(Target.campaign_id == cid)).all()
    assert sorted(t.user_id for t in targets) == sorted(uids)
    assert len({t.token for t in targets}) == 3


def test_seed_users_is_bounded_and_audited(client, session_factory):
    client.post("/users/seed", data={"count": 0})        # clamped up to 1
    client.post("/users/seed", data={"count": 25})
    with session_factory() as s:
        users = s.exec(select(User)).all()
        groups = {g.name for g in s.exec(select(StaffGroup)).all()}
    assert len(users) == 26
    assert len({u.email for u in users}) == 26
    assert {"New staff", "Failed phishing - this month"} <= groups
    assert client.get("/users").status_code == 200


def test_reports_dashboard_render_after_activity(client, anon, session_factory):
    cid, _, token = _targeted(client, session_factory)
    client.post(f"/campaigns/{cid}/send")
    anon.get(f"/t/open/{token}.png")
    anon.get(f"/t/click/{token}", headers={"user-agent": "Mozilla/5.0 Chrome/125.0"})
    anon.get(f"/t/report/{token}")
    for path in ("/", "/phishing", "/reports", f"/campaigns/{cid}"):
        assert client.get(path).status_code == 200


@pytest.mark.parametrize("seconds,expected", [
    (None, "—"), (4.25, "4.2s"), (59.9, "59.9s"), (60, "1m"), (3599, "59m"),
    (3600, "1h"), (3660, "1h 1m"), (86400, "1d"), (90000, "1d 1h"),
])
def test_humandur(seconds, expected):
    assert humandur(seconds) == expected


def test_prod_config_rejects_missing_secrets():
    problems = Settings(env="prod", secret_key="", admin_password="",
                        smtp_host="").validate_for_runtime()
    assert len(problems) == 3
    ok = Settings(env="prod", secret_key="k", admin_password="p",
                  smtp_host="smtp.example.com").validate_for_runtime()
    assert ok == []
    assert Settings(env="dev").validate_for_runtime() == []


async def test_smtp_send_strips_header_injection(monkeypatch):
    sent = {}

    async def fake_send(msg, **kwargs):
        sent["msg"], sent["kwargs"] = msg, kwargs

    monkeypatch.setattr(mailer.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(mailer.aiosmtplib, "send", fake_send)
    campaign = Campaign(name="C", from_name="IT\r\nBcc: evil@x.com",
                        from_email="it@example.com", subject="Hi")
    target = Target(campaign_id=1, user_id=1, email="p@example.com",
                    name="Pat\nBcc: evil@x.com", token="tok", consented=True)
    await mailer.send_campaign_email(campaign, target)
    msg = sent["msg"]
    assert "\n" not in msg["From"] and "\n" not in msg["To"]
    assert msg["Bcc"] is None
    assert sent["kwargs"]["hostname"] == "smtp.example.com"


async def test_send_refuses_non_consenting_target():
    target = Target(campaign_id=1, user_id=1, email="p@example.com", token="t",
                    consented=False)
    with pytest.raises(PermissionError):
        await mailer.send_campaign_email(Campaign(name="C"), target)
