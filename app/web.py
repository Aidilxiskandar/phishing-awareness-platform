"""Shared web-layer objects used by every router: templates, logging, audit, client IP."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app import security
from app.database import get_session
from app.models import (
    AuditLog,
)

logger = logging.getLogger("phishguard")

# Templates live next to the app package; resolve absolutely so the app works
# from any working directory.
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def client_ip(request: Request) -> str:
    """Client IP for the evidence log (see security.client_ip: X-Forwarded-For is
    only honoured from TRUSTED_PROXIES, walked right-to-left, so a client can't
    forge the address written into the evidence)."""
    return security.client_ip(request)


def record_audit(request: Request, action: str, detail: str = "") -> None:
    """Append an audit entry for a privileged admin action (best-effort)."""
    try:
        actor = request.session.get("admin", "?")
    except (AssertionError, KeyError):
        actor = "?"
    try:
        with get_session() as session:
            session.add(AuditLog(actor=actor, action=action,
                                 detail=detail[:300], ip=client_ip(request)))
            session.commit()
        logger.info("audit action=%s actor=%s detail=%s", action, actor, detail[:120])
    except Exception:
        logger.exception("audit write failed for action=%s", action)


def humandur(seconds: float | None) -> str:
    """Render 'seconds since send' as a readable duration: 7.2s, 56m, 1h 12m."""
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    if mins < 60:
        return f"{mins}m"
    hours, rem = divmod(mins, 60)
    if hours < 24:
        return f"{hours}h {rem}m" if rem else f"{hours}h"
    days, rh = divmod(hours, 24)
    return f"{days}d {rh}h" if rh else f"{days}d"


templates.env.filters["humandur"] = humandur
security.install_template_globals(templates.env)
