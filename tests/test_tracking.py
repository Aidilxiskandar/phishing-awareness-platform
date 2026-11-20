"""Tracking endpoints: open/click/confirm/report classification + token handling."""
from sqlmodel import select

from app.models import Campaign, Event, EventType, Target, User, Verdict

CHROME = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def _make_target(client, session_factory) -> tuple[int, str]:
    client.post("/users", data={"email": "t@example.com", "name": "T", "consented": "on"})
    client.post("/campaigns", data={"name": "C", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
        cid = s.exec(select(Campaign.id)).first()
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    with session_factory() as s:
        token = s.exec(select(Target.token)).first()
    return cid, token


def _events(session_factory, etype=None):
    with session_factory() as s:
        evs = s.exec(select(Event)).all()
    return [e for e in evs if etype is None or e.type == etype]


def test_unknown_click_token_404(anon):
    assert anon.get("/t/click/nope").status_code == 404


def test_open_pixel_served_and_logged(client, anon, session_factory):
    _, token = _make_target(client, session_factory)
    r = anon.get(f"/t/open/{token}.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(_events(session_factory, EventType.OPEN)) == 1


def test_scanner_user_agent_classified_scanner(client, anon, session_factory):
    _, token = _make_target(client, session_factory)
    anon.get(f"/t/click/{token}", headers={"user-agent": "curl/8.4.0"})
    clicks = _events(session_factory, EventType.CLICK)
    assert len(clicks) == 1
    assert clicks[0].verdict == Verdict.SCANNER


def test_browser_click_then_confirm_is_human(client, anon, session_factory):
    _, token = _make_target(client, session_factory)
    anon.get(f"/t/click/{token}", headers={"user-agent": CHROME})
    anon.post(f"/t/confirm/{token}", headers={"user-agent": CHROME})
    clicks = _events(session_factory, EventType.CLICK)
    assert clicks[0].verdict == Verdict.HUMAN


def test_report_logs_report_event(client, anon, session_factory):
    _, token = _make_target(client, session_factory)
    r = anon.get(f"/t/report/{token}")
    assert r.status_code == 200
    assert len(_events(session_factory, EventType.REPORT)) == 1


def test_forged_xff_ignored_without_trusted_proxy(client, anon, session_factory):
    _, token = _make_target(client, session_factory)
    anon.get(f"/t/click/{token}",
             headers={"user-agent": CHROME, "x-forwarded-for": "1.2.3.4"})
    clicks = _events(session_factory, EventType.CLICK)
    # No trusted proxy configured -> the forged XFF must not be recorded as the IP.
    assert clicks[0].ip != "1.2.3.4"
