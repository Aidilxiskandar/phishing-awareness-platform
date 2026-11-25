"""Session, CSRF, brute-force, header and client-IP protections."""
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import security
from app.main import app
from tests.conftest import csrf_from, login

# --- CSRF ---------------------------------------------------------------------


def test_login_without_csrf_token_is_refused(raw):
    r = raw.post("/login", data={"username": "admin", "password": "testpass", "next": "/"})
    assert r.status_code == 403


def test_admin_post_without_token_is_refused(client):
    del client.headers[security.CSRF_HEADER]
    r = client.post("/users", data={"email": "x@example.com"})
    assert r.status_code == 403


def test_admin_post_with_wrong_token_is_refused(client):
    client.headers[security.CSRF_HEADER] = "forged"
    assert client.post("/users", data={"email": "x@example.com"}).status_code == 403


def test_form_field_token_is_accepted(client):
    token = client.headers.pop(security.CSRF_HEADER)
    r = client.post("/users", data={"email": "f@example.com", "csrf_token": token},
                    follow_redirects=False)
    assert r.status_code == 303


def test_browser_same_origin_post_is_accepted(client):
    """Regression: real browsers send Origin on form POSTs. Under the old
    Referrer-Policy: no-referrer that Origin was "null" and every admin form
    in a real browser failed the CSRF check (tests never sent an Origin)."""
    r = client.post("/users", data={"email": "o@example.com"},
                    headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/users").headers["Referrer-Policy"] == "same-origin"


def test_null_origin_is_refused(client):
    r = client.post("/users", data={"email": "x@example.com"}, headers={"Origin": "null"})
    assert r.status_code == 403


def test_cross_origin_post_is_refused_even_with_token(client):
    r = client.post("/users", data={"email": "x@example.com"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_every_admin_form_carries_a_csrf_field(client):
    for path in ("/phishing", "/users"):
        html = client.get(path).text
        forms = re.findall(r'<form\b[^>]*method="post"[^>]*>(.*?)</form>', html, flags=re.S)
        assert forms, path
        assert all('name="csrf_token"' in f for f in forms), path


def test_tracking_endpoints_need_no_csrf_token(raw):
    # Recipients' mail clients and the landing beacon can't hold a token.
    assert raw.post("/t/confirm/unknown").status_code == 404  # not 403


# --- sessions -----------------------------------------------------------------


def test_login_rotates_the_session_csrf_token():
    with TestClient(app) as c:
        before = csrf_from(c, "/login")
        assert login(c).status_code == 303
        after = csrf_from(c, "/")
    assert before != after


def test_logged_out_cookie_cannot_be_replayed():
    with TestClient(app) as c:
        assert login(c).status_code == 303
        stolen = dict(c.cookies)
        assert c.post("/logout", follow_redirects=False).status_code == 303
    with TestClient(app, cookies=stolen) as replay:
        r = replay.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_session_expires_after_max_age(client, monkeypatch):
    import time as _time
    real = _time.time
    monkeypatch.setattr(security.time, "time", lambda: real() + security.SESSION_MAX_AGE + 1)
    assert client.get("/", follow_redirects=False).status_code == 303


def test_logout_requires_post(client):
    assert client.get("/logout").status_code == 405


# --- brute force --------------------------------------------------------------


def test_repeated_failures_lock_the_login(anon):
    for _ in range(security.LOGIN_MAX_FAILURES):
        assert login(anon, password="wrong").status_code == 401
    r = login(anon)  # correct password, but locked out
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_successful_login_resets_failure_count(anon):
    for _ in range(security.LOGIN_MAX_FAILURES - 1):
        login(anon, password="wrong")
    assert login(anon).status_code == 303
    anon.post("/logout")
    for _ in range(security.LOGIN_MAX_FAILURES - 1):
        assert login(anon, password="wrong").status_code == 401


def test_throttle_unlocks_after_lockout():
    t = security.LoginThrottle(max_failures=2, window=60, lockout=30)
    t.record_failure("1.2.3.4", "admin", now=0)
    t.record_failure("1.2.3.4", "admin", now=1)
    assert t.retry_after("1.2.3.4", "admin", now=2) > 0
    assert t.retry_after("9.9.9.9", "ADMIN ", now=2) > 0  # username key, case-folded
    assert t.retry_after("1.2.3.4", "admin", now=40) == 0


def test_credential_check_survives_non_ascii_input(anon):
    # secrets.compare_digest raises on non-ASCII str; we must answer 401, not 500.
    assert login(anon, username="ädmin", password="pässwörd").status_code == 401


# --- redirects ----------------------------------------------------------------


@pytest.mark.parametrize("target", [
    "//evil.example", "/\\evil.example", "https://evil.example", "javascript:alert(1)",
    "/ok\r\nSet-Cookie: x=1", "", None,
])
def test_safe_next_rejects_hostile_targets(target):
    assert security.safe_next(target) == "/"


def test_safe_next_keeps_local_paths():
    assert security.safe_next("/campaigns/3?x=1") == "/campaigns/3?x=1"


# --- headers ------------------------------------------------------------------


def test_csp_nonce_matches_inline_scripts(client):
    r = client.get("/phishing")
    csp = r.headers["Content-Security-Policy"]
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    scripts = re.findall(r"<script\b([^>]*)>", r.text)
    assert scripts and all(f'nonce="{nonce}"' in attrs for attrs in scripts)
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]


def test_no_inline_event_handlers_in_pages(client):
    for path in ("/", "/phishing", "/users", "/training", "/reports"):
        assert not re.search(r"\son[a-z]+=", client.get(path).text), path


def test_admin_pages_are_not_cached(client):
    assert client.get("/users").headers["Cache-Control"] == "no-store"


def test_raw_email_preview_is_sandboxed(client):
    r = client.get("/templates/password-expiry/email")
    assert r.status_code == 200
    assert r.headers["Content-Security-Policy"].startswith("sandbox")


# --- client IP ----------------------------------------------------------------


def _req(peer, xff=None):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_xff_ignored_without_trusted_proxy(monkeypatch):
    monkeypatch.setattr(security.settings, "trusted_proxies", "")
    assert security.client_ip(_req("203.0.113.5", "1.1.1.1")) == "203.0.113.5"


def test_spoofed_left_most_xff_is_not_trusted(monkeypatch):
    monkeypatch.setattr(security.settings, "trusted_proxies", "10.0.0.0/8")
    # Client sent "6.6.6.6"; our proxy appended the real peer 198.51.100.7.
    req = _req("10.0.0.2", "6.6.6.6, 198.51.100.7")
    assert security.client_ip(req) == "198.51.100.7"


def test_malformed_xff_falls_back_to_peer(monkeypatch):
    monkeypatch.setattr(security.settings, "trusted_proxies", "10.0.0.2")
    assert security.client_ip(_req("10.0.0.2", "not-an-ip")) == "10.0.0.2"
