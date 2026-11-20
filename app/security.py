"""Authentication / request-guard helpers.

The admin surface is protected deny-by-default by a single middleware (see
app/main.py): every path that is not explicitly public requires a logged-in
admin session, and every state-changing request must pass a same-origin CSRF
check. Public paths are the tracking endpoints (hit by recipients), static
assets, the health check, and the login/logout routes themselves.
"""
from __future__ import annotations

import secrets
from urllib.parse import urlparse

from starlette.requests import Request

from app.config import settings

# Paths reachable without an admin session. Everything else is protected.
PUBLIC_PREFIXES = ("/t/", "/static/", "/favicon")
PUBLIC_EXACT = {"/health", "/login", "/logout"}

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time check against the single configured admin credential."""
    expected_pw = settings.effective_admin_password
    if not expected_pw:
        return False  # prod with no password set -> no login possible
    user_ok = secrets.compare_digest(username, settings.admin_username)
    pw_ok = secrets.compare_digest(password, expected_pw)
    return user_ok and pw_ok


def is_authenticated(request: Request) -> bool:
    try:
        return bool(request.session.get("admin"))
    except (AssertionError, KeyError):
        # SessionMiddleware not installed (shouldn't happen) -> treat as anonymous.
        return False


def csrf_ok(request: Request) -> bool:
    """Same-origin check for state-changing requests.

    Browsers send Origin (or at least Referer) on form POSTs; we require its host
    to match ours. Non-browser clients that send neither are allowed — the
    SameSite=Lax session cookie already blocks cross-site form posts in browsers.
    """
    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    if origin:
        return urlparse(origin).netloc == host
    referer = request.headers.get("referer")
    if referer:
        return urlparse(referer).netloc == host
    return True


def safe_next(target: str | None) -> str:
    """Prevent open-redirect: only allow local, single-slash paths."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return "/"
