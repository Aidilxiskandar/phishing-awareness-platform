"""Login, logout and the health probe."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from sqlmodel import select

from app import security
from app.config import settings
from app.database import get_session
from app.models import (
    User,
)
from app.web import client_ip, logger, record_audit, templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {
        "next": security.safe_next(next), "error": None,
        "tab": None, "dry_run": settings.dry_run,
    })


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...),
          next: str = Form("/")):
    ip = client_ip(request)

    def _fail(message: str, status: int, headers: dict | None = None):
        return templates.TemplateResponse(request, "login.html", {
            "next": security.safe_next(next), "error": message, "tab": None,
            "dry_run": settings.dry_run,
        }, status_code=status, headers=headers)

    wait = security.login_throttle.retry_after(ip, username)
    if wait:
        logger.warning("login_locked user=%s ip=%s retry_after=%s", username[:64], ip, wait)
        return _fail(f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s).",
                     429, {"Retry-After": str(wait)})
    if not security.verify_credentials(username, password):
        security.login_throttle.record_failure(ip, username)
        logger.warning("login_failed user=%s ip=%s", username[:64], ip)
        return _fail("Invalid username or password.", 401)
    security.login_throttle.reset(ip, username)
    security.start_session(request, settings.admin_username)
    record_audit(request, "login", f"admin '{username}' signed in")
    return RedirectResponse(security.safe_next(next), status_code=303)


@router.post("/logout")
def logout(request: Request):
    if security.is_authenticated(request):
        record_audit(request, "logout", "admin signed out")
    security.end_session(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Browsers ask for /favicon.ico regardless of <link rel=icon>; serve the SVG."""
    path = Path(__file__).resolve().parent.parent / "static" / "favicon.svg"
    return FileResponse(path, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/health")
def health():
    """Liveness/readiness probe: confirms the app and DB respond."""
    try:
        with get_session() as session:
            session.exec(select(User.id).limit(1)).all()
        return {"status": "ok"}
    except Exception:
        return JSONResponse({"status": "degraded"}, status_code=503)
