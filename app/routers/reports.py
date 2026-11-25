"""Reports tab: risk scores, evidence log, admin activity and CSV export."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Request
from fastapi.responses import (
    HTMLResponse,
    StreamingResponse,
)
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.models import (
    AuditLog,
    Campaign,
    Event,
    Target,
    utcnow,
)
from app.services.analytics import campaign_report, reports_overview
from app.services.risk import risk_scores as _risk_scores
from app.web import record_audit, templates

router = APIRouter()


def _csv_safe(value) -> str:
    """Neutralise CSV formula injection: a cell starting with = + - @ (or a tab/CR
    before them) is executed by spreadsheet apps, so prefix it with a quote."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


@router.get("/reports", response_class=HTMLResponse)
def reports(request: Request):
    with get_session() as session:
        risk = _risk_scores(session)
        events = session.exec(
            select(Event).order_by(Event.id.desc()).limit(200)
        ).all()
        targets = session.exec(select(Target)).all()
        campaigns = session.exec(select(Campaign)).all()
        audit = session.exec(select(AuditLog).order_by(AuditLog.id.desc()).limit(20)).all()
        target_by_id = {t.id: t for t in targets}
        campaign_by_id = {c.id: c for c in campaigns}
        overview = reports_overview(session)
    return templates.TemplateResponse(request, "reports.html", {
        "tab": "reports", "risk": risk, "events": events, "audit": audit,
        "target_by_id": target_by_id, "campaign_by_id": campaign_by_id, "dry_run": settings.dry_run,
        **overview,
    })


@router.get("/reports/campaigns/{cid}", response_class=HTMLResponse)
def campaign_report_page(request: Request, cid: int):
    """Print-ready executive report for one campaign (browser "Save as PDF")."""
    with get_session() as session:
        report = campaign_report(session, cid)
    if report is None:
        return HTMLResponse("Campaign not found", status_code=404)
    return templates.TemplateResponse(request, "report_campaign.html", {
        "tab": "reports", "dry_run": settings.dry_run, "generated_at": utcnow(), **report,
    })


@router.get("/reports/export.csv")
def export_csv(request: Request):
    record_audit(request, "users.export", "evidence CSV downloaded")
    with get_session() as session:
        events = session.exec(select(Event).order_by(Event.id)).all()
        targets = {t.id: t for t in session.exec(select(Target)).all()}
        campaigns = {c.id: c for c in session.exec(select(Campaign)).all()}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp_utc", "campaign", "recipient_email", "type", "verdict",
                "reason", "ip", "user_agent", "http_method", "seconds_since_send"])
    for e in events:
        t = targets.get(e.target_id)
        c = campaigns.get(e.campaign_id)
        # Attacker-controllable fields (name/email/reason/user_agent) are escaped
        # against spreadsheet formula injection.
        w.writerow([_csv_safe(x) for x in (
            e.created_at.isoformat(),
            c.name if c else e.campaign_id,
            t.email if t else e.target_id,
            e.type.value, e.verdict.value, e.reason, e.ip, e.user_agent,
            e.http_method,
            f"{e.seconds_since_send:.1f}" if e.seconds_since_send is not None else "",
        )])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=phishing_evidence.csv"},
    )
