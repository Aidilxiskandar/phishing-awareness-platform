"""Send-flow safety: idempotency, per-target state, live consent re-check."""
from sqlmodel import select

from app.models import Campaign, CampaignStatus, Target, User


def _setup(client, session_factory, consented=True) -> int:
    client.post("/users", data={"email": "a@example.com", "name": "A",
                                "consented": "on" if consented else "off"})
    client.post("/campaigns", data={"name": "C", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
        cid = s.exec(select(Campaign.id)).first()
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    return cid


def test_send_marks_sent_and_stamps_each_target(client, session_factory):
    cid = _setup(client, session_factory, consented=True)
    client.post(f"/campaigns/{cid}/send")
    with session_factory() as s:
        campaign = s.get(Campaign, cid)
        target = s.exec(select(Target).where(Target.campaign_id == cid)).first()
    assert campaign.status == CampaignStatus.SENT
    assert target.sent_at is not None
    assert target.send_error == ""


def test_resend_is_blocked_and_does_not_restamp(client, session_factory):
    cid = _setup(client, session_factory, consented=True)
    client.post(f"/campaigns/{cid}/send")
    with session_factory() as s:
        first_sent = s.exec(select(Target).where(Target.campaign_id == cid)).first().sent_at

    r = client.post(f"/campaigns/{cid}/send", follow_redirects=False)
    assert "notice=already_sent" in r.headers["location"]
    with session_factory() as s:
        again = s.exec(select(Target).where(Target.campaign_id == cid)).first().sent_at
    assert again == first_sent  # not re-sent


def test_non_consenting_target_is_skipped_with_reason(client, session_factory):
    cid = _setup(client, session_factory, consented=False)
    client.post(f"/campaigns/{cid}/send")
    with session_factory() as s:
        target = s.exec(select(Target).where(Target.campaign_id == cid)).first()
        campaign = s.get(Campaign, cid)
    assert target.sent_at is None
    assert "not marked as consenting" in target.send_error
    assert campaign.status == CampaignStatus.SENT  # campaign still completes
