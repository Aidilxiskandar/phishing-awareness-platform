"""The ethics/consent gate — the safety-critical heart of a dual-use tool."""
import pytest

from app.mailer import send_campaign_email
from app.models import Campaign, Target, User


def test_user_consent_defaults_to_false():
    # Opt-in, fail-closed: a brand-new user cannot be phished by default.
    assert User(email="a@example.com").consented is False


def test_target_consent_defaults_to_false():
    assert Target(campaign_id=1, user_id=1, email="a@example.com", token="x").consented is False


async def test_send_refuses_non_consenting_recipient():
    campaign = Campaign(name="c", from_name="IT", from_email="it@example.com")
    target = Target(campaign_id=1, user_id=1, email="a@example.com",
                    token="tok", consented=False)
    with pytest.raises(PermissionError):
        await send_campaign_email(campaign, target)


async def test_dry_run_consenting_does_not_touch_smtp(monkeypatch):
    import aiosmtplib
    calls = {"n": 0}

    async def fake_send(*a, **k):
        calls["n"] += 1

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    campaign = Campaign(name="c", from_name="IT", from_email="it@example.com")
    target = Target(campaign_id=1, user_id=1, email="a@example.com",
                    token="tok", consented=True)
    await send_campaign_email(campaign, target)  # dry-run in tests -> no SMTP
    assert calls["n"] == 0
