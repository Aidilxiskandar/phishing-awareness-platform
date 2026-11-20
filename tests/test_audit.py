"""Audit trail + observability: privileged actions are recorded; request IDs set."""
from sqlmodel import select

from app.models import AuditLog, Campaign, User


def _actions(session_factory):
    with session_factory() as s:
        return [a.action for a in s.exec(select(AuditLog)).all()]


def test_login_is_audited(client, session_factory):
    assert "login" in _actions(session_factory)


def test_campaign_create_and_send_are_audited(client, session_factory):
    client.post("/users", data={"email": "a@example.com", "name": "A", "consented": "on"})
    client.post("/campaigns", data={"name": "C", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
        cid = s.exec(select(Campaign.id)).first()
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    client.post(f"/campaigns/{cid}/send")
    actions = _actions(session_factory)
    assert "campaign.create" in actions
    assert "campaign.send" in actions


def test_csv_export_is_audited(client, session_factory):
    client.get("/reports/export.csv")
    assert "users.export" in _actions(session_factory)


def test_request_id_header_present(client):
    assert client.get("/").headers.get("x-request-id")


def test_invalid_email_rejected(client, session_factory):
    client.post("/users", data={"email": "not-an-email", "name": "X", "consented": "on"},
                follow_redirects=False)
    with session_factory() as s:
        users = s.exec(select(User)).all()
    assert all(u.email != "not-an-email" for u in users)
