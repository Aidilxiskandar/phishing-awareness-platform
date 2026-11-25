"""Dashboard tab: KPIs across everything plus recent activity."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import (
    HTMLResponse,
)
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.models import (
    Campaign,
    CampaignStatus,
    Event,
    EventType,
    QuizResult,
    Target,
    User,
    Verdict,
)
from app.services.charts import donut as _donut
from app.services.charts import trend as _trend
from app.services.risk import risk_scores as _risk_scores
from app.web import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with get_session() as session:
        users = session.exec(select(User)).all()
        campaigns = session.exec(select(Campaign)).all()
        targets = session.exec(select(Target)).all()
        events = session.exec(select(Event)).all()
        results = session.exec(select(QuizResult)).all()
        risk_rows = _risk_scores(session)

        sent_targets = len(targets)
        human_clicks = sum(1 for e in events if e.type == EventType.CLICK and e.verdict == Verdict.HUMAN)
        scanner_clicks = sum(1 for e in events if e.type == EventType.CLICK and e.verdict == Verdict.SCANNER)
        reports = sum(1 for e in events if e.type == EventType.REPORT)
        click_rate = (human_clicks / sent_targets * 100) if sent_targets else 0.0

        # Distinct targets per funnel stage (a person counted once per stage).
        opened_ids = {e.target_id for e in events if e.type == EventType.OPEN}
        clicked_ids = {e.target_id for e in events
                       if e.type == EventType.CLICK and e.verdict == Verdict.HUMAN}
        reported_ids = {e.target_id for e in events if e.type == EventType.REPORT}

        # Per-campaign phish-prone trend (ordered by when the drill went out).
        camp_targets: dict[int, set[int]] = {}
        for t in targets:
            camp_targets.setdefault(t.campaign_id, set()).add(t.id)
        sent_campaigns = [c for c in campaigns
                          if camp_targets.get(c.id) and c.status == CampaignStatus.SENT]
        sent_campaigns.sort(key=lambda c: (c.sent_at or c.created_at))
        trend_series = []
        for c in sent_campaigns:
            tids = camp_targets.get(c.id, set())
            hc = len({e.target_id for e in events if e.target_id in tids
                      and e.type == EventType.CLICK and e.verdict == Verdict.HUMAN})
            trend_series.append({"name": c.name, "rate": (hc / len(tids) * 100) if tids else 0.0,
                                 "targets": len(tids), "clicks": hc})

        recent = sorted(events, key=lambda e: e.id or 0, reverse=True)[:10]
        target_by_id = {t.id: t for t in targets}

    # Risk distribution over people actually tested (ignore untargeted directory).
    tested = [r for r in risk_rows if r["campaigns"] > 0]
    band_count = {b: sum(1 for r in tested if r["band"] == b) for b in ("High", "Medium", "Low")}
    top_risk = [r for r in tested if r["score"] > 0][:6]

    # Phish-prone delta: latest campaign vs the one before it.
    delta = None
    if len(trend_series) >= 2:
        delta = trend_series[-1]["rate"] - trend_series[-2]["rate"]

    charts = {
        "funnel": [
            {"label": "Delivered", "value": sent_targets, "color": "var(--n2)"},
            {"label": "Opened", "value": len(opened_ids), "color": "var(--n3)"},
            {"label": "Clicked (human)", "value": len(clicked_ids), "color": "var(--red)"},
            {"label": "Reported", "value": len(reported_ids), "color": "var(--green)"},
        ],
        "risk_donut": _donut([
            {"label": "High", "value": band_count["High"], "color": "var(--red)"},
            {"label": "Medium", "value": band_count["Medium"], "color": "var(--amber)"},
            {"label": "Low", "value": band_count["Low"], "color": "var(--n2)"},
        ]),
        "accuracy": {"human": human_clicks, "scanner": scanner_clicks, "reported": reports,
                     "total_clicks": human_clicks + scanner_clicks},
        "trend": _trend(trend_series),
        "trend_series": trend_series,
        "delta": delta,
        "top_risk": top_risk,
        "tested_count": len(tested),
    }

    stats = {
        "users": len(users),
        "campaigns": len(campaigns),
        "sent": sent_targets,
        "human_clicks": human_clicks,
        "scanner_clicks": scanner_clicks,
        "reports": reports,
        "click_rate": click_rate,
        "trainings_done": len(results),
    }
    return templates.TemplateResponse(request, "dashboard.html", {
        "tab": "dashboard", "stats": stats, "charts": charts,
        "recent": recent, "target_by_id": target_by_id, "dry_run": settings.dry_run,
    })
