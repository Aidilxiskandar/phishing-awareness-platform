"""Auth guard: deny-by-default, login, public endpoints, security headers."""


def test_anonymous_admin_page_redirects_to_login(anon):
    r = anon.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_anonymous_csv_export_is_protected(anon):
    r = anon.get("/reports/export.csv", follow_redirects=False)
    assert r.status_code == 303


def test_anonymous_post_is_rejected_not_redirected(anon):
    # State-changing requests must not be silently redirected.
    r = anon.post("/campaigns",
                  data={"name": "x", "subject": "s", "from_name": "IT", "from_email": "a@b.com"},
                  follow_redirects=False)
    assert r.status_code == 401


def test_bad_credentials_rejected(anon):
    r = anon.post("/login", data={"username": "admin", "password": "wrong", "next": "/"})
    assert r.status_code == 401


def test_login_then_access_dashboard(client):
    assert client.get("/").status_code == 200


def test_logout_clears_session(client):
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303


def test_health_is_public(anon):
    r = anon.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_open_redirect_blocked_on_next(anon):
    r = anon.post("/login",
                  data={"username": "admin", "password": "testpass", "next": "//evil.com"},
                  follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"  # not //evil.com


def test_security_headers_present(client):
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
