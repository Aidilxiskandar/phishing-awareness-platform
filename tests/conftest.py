"""Shared test fixtures.

Environment is set BEFORE importing the app so the engine binds to a throwaway
temp SQLite file and a known admin credential. Each test runs against a fresh,
re-seeded schema.
"""
import os
import tempfile

_TMPDIR = tempfile.mkdtemp(prefix="phishguard-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMPDIR}/test.db")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "testpass")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-prod")
os.environ.setdefault("ENV", "dev")

import re  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app import security  # noqa: E402
from app.database import engine, get_session, init_db  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = {"username": "admin", "password": "testpass"}


_CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf_from(client: TestClient, path: str = "/login") -> str:
    """Load a page like a browser would and return the session's CSRF token."""
    m = _CSRF_RE.search(client.get(path).text)
    assert m, f"no CSRF token on {path}"
    return m.group(1)


def arm_csrf(client: TestClient, path: str = "/login") -> TestClient:
    """Send the session's CSRF token on every request (the header form)."""
    client.headers[security.CSRF_HEADER] = csrf_from(client, path)
    return client


def login(client: TestClient, **creds):
    """Log in through the real form flow and re-arm the (rotated) CSRF token."""
    arm_csrf(client, "/login")
    r = client.post("/login", data={**ADMIN, "next": "/", **creds}, follow_redirects=False)
    if r.status_code == 303:
        arm_csrf(client, "/")  # start_session() mints a fresh token
    return r


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset + re-seed the schema and in-memory security state around every test."""
    SQLModel.metadata.drop_all(engine)
    security.login_throttle.clear()
    security.clear_revocations()
    init_db()
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def anon():
    """An unauthenticated client that has loaded the login page, so it holds a
    CSRF token like a real browser (for public tracking/login endpoints)."""
    with TestClient(app) as c:
        yield arm_csrf(c, "/login")


@pytest.fixture
def raw():
    """An unauthenticated client with no CSRF token at all."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client():
    """A logged-in admin client."""
    with TestClient(app) as c:
        r = login(c)
        assert r.status_code == 303, r.text
        yield c


@pytest.fixture
def session_factory():
    """Direct DB access for arranging/asserting state in tests."""
    return get_session
