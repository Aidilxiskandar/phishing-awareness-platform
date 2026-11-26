"""DEMO_MODE: a public demo must never send email and must stay usable."""
import asyncio
from types import SimpleNamespace

import pytest

from app import security
from app.config import Settings
from app.web import templates


def test_demo_mode_forces_dry_run_even_with_smtp():
    s = Settings(demo_mode=True, smtp_host="smtp.example.com")
    assert s.dry_run is True


def test_demo_mode_with_smtp_refuses_to_start():
    s = Settings(demo_mode=True, smtp_host="smtp.example.com")
    assert any("DEMO_MODE" in p for p in s.validate_for_runtime())


def test_prod_demo_without_smtp_is_a_valid_config():
    s = Settings(env="prod", demo_mode=True, secret_key="x" * 40, admin_password="y" * 20)
    assert s.validate_for_runtime() == []


def test_prod_without_demo_still_requires_smtp():
    s = Settings(env="prod", secret_key="x" * 40, admin_password="y" * 20)
    assert any("SMTP" in p for p in s.validate_for_runtime())


def test_demo_send_never_reaches_smtp(monkeypatch, capsys):
    from app import mailer
    monkeypatch.setattr(mailer.settings, "demo_mode", True)
    monkeypatch.setattr(mailer.settings, "smtp_host", "smtp.example.com")

    async def boom(*a, **k):
        raise AssertionError("demo mode tried to send real email")
    monkeypatch.setattr(mailer.aiosmtplib, "send", boom)
    campaign = SimpleNamespace(subject="S", from_name="IT", from_email="it@example.com",
                               body="", cta_label="")
    target = SimpleNamespace(token="tok", name="N", email="n@example.com", consented=True)
    asyncio.run(mailer.send_campaign_email(campaign, target))
    assert "[DRY-RUN]" in capsys.readouterr().out


def test_demo_throttle_is_per_ip_only():
    t = security.LoginThrottle(max_failures=2, per_user=False)
    t.record_failure("1.1.1.1", "admin", now=0)
    t.record_failure("1.1.1.1", "admin", now=1)
    assert t.retry_after("1.1.1.1", "admin", now=2) > 0       # the guessing IP is locked
    assert t.retry_after("2.2.2.2", "admin", now=2) == 0      # everyone else can still log in


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(security.settings, "demo_mode", True)
    monkeypatch.setitem(templates.env.globals, "demo_mode", True)


def test_login_page_shows_demo_credentials(anon, demo_on):
    html = anon.get("/login").text
    assert "Public demo." in html and "<code>admin</code>" in html


def test_login_page_hides_credentials_outside_demo(anon):
    assert "Public demo." not in anon.get("/login").text


def test_demo_badge_on_admin_pages(client, demo_on):
    assert "Public demo · no email is ever sent" in client.get("/").text
