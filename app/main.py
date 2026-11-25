"""FastAPI app: five-tab admin UI + tracking endpoints.

Tabs:
  /            Dashboard  - KPIs across everything + recent activity
  /phishing    Phishing   - campaigns: create, list, detail, send
  /training    Training   - micro-lessons + quizzes, and who has completed them
  /users       Users      - the global people directory
  /reports     Reports    - per-person risk scores, full evidence log, CSV export

Tracking (hit by the email / landing page):
  GET  /t/open/{token}.png    1x1 pixel -> logs an OPEN
  GET/HEAD /t/click/{token}   tracked link -> logs a CLICK, classifies, shows landing page
  POST /t/confirm/{token}     JS beacon from landing page -> logs CONFIRM, upgrades to HUMAN
  GET  /t/report/{token}      recipient reported the email -> logs REPORT
"""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import security
from app.config import settings
from app.database import init_db
from app.routers import auth, dashboard, phishing, reports, tracking, training, users
from app.web import humandur, logger  # noqa: F401  (humandur re-exported for callers)


def _configure_logging() -> None:
    # Structured-ish single-line logs with a timestamp, level, logger and message.
    # Idempotent: only installs a handler once.
    root = logging.getLogger()
    if not any(getattr(h, "_phishguard", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"))
        handler._phishguard = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_logging()
    problems = settings.validate_for_runtime()
    if problems:
        raise RuntimeError("Fatal configuration error(s): " + "; ".join(problems))
    init_db()
    logger.info("startup env=%s dry_run=%s", settings.env, settings.dry_run)
    yield


app = FastAPI(
    title="PhishGuard — Phishing Awareness Platform",
    version="2.4.0",
    lifespan=lifespan,
    # Hide the interactive API schema in production.
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None if settings.is_prod else "/redoc",
    openapi_url=None if settings.is_prod else "/openapi.json",
)

# Self-hosted static assets (training videos, posters, etc.).
STATIC_DIR = Path(__file__).resolve().parent / "static"
(STATIC_DIR / "videos").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- Request guard: deny-by-default auth + CSRF + security headers -----------

@app.middleware("http")
async def _guard(request: Request, call_next):
    request_id = secrets.token_hex(8)
    request.state.request_id = request_id
    nonce = security.new_csp_nonce()
    request.state.csp_nonce = nonce
    path = request.url.path
    if not security.is_public_path(path) and not security.is_authenticated(request):
        if request.method == "GET":
            return RedirectResponse(security.login_redirect_url(path), status_code=303)
        return Response("Authentication required", status_code=401)
    # Every state-changing request outside the recipient tracking endpoints
    # (including the login form itself) needs a session-bound CSRF token.
    if security.csrf_required(request) and not await security.csrf_ok(request):
        logger.warning("csrf_block rid=%s path=%s", request_id, path)
        return Response("CSRF check failed. Reload the page and try again.", status_code=403)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    for name, value in security.security_headers(path, nonce).items():
        response.headers.setdefault(name, value)
    return response


# SessionMiddleware is added AFTER the guard so it wraps it (runs first) and
# request.session is populated before the guard reads it.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.effective_secret_key,
    session_cookie=security.SESSION_COOKIE,
    max_age=security.SESSION_MAX_AGE,
    same_site="lax",
    https_only=settings.is_prod,
)

for _module in (auth, dashboard, phishing, users, training, reports, tracking):
    app.include_router(_module.router)
