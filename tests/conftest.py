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

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.database import engine, get_session, init_db  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = {"username": "admin", "password": "testpass"}


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset + re-seed the schema around every test."""
    SQLModel.metadata.drop_all(engine)
    init_db()
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def anon():
    """An unauthenticated client (for public tracking/login endpoints)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client():
    """A logged-in admin client."""
    with TestClient(app) as c:
        r = c.post("/login", data={**ADMIN, "next": "/"}, follow_redirects=False)
        assert r.status_code == 303, r.text
        yield c


@pytest.fixture
def session_factory():
    """Direct DB access for arranging/asserting state in tests."""
    return get_session
