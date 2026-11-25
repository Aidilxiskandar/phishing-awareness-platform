"""Recipient-facing tracking endpoints (public, hit by email clients and the landing page).

  GET  /t/open/{token}.png    1x1 pixel -> logs an OPEN
  GET/HEAD /t/click/{token}   tracked link -> logs a CLICK, classifies, shows landing page
  POST /t/confirm/{token}     JS beacon from landing page -> logs CONFIRM, upgrades to HUMAN
  GET  /t/report/{token}      recipient reported the email -> logs REPORT
"""
from __future__ import annotations

import base64
from datetime import UTC

from fastapi import APIRouter, Request
from fastapi.responses import (
    HTMLResponse,
    Response,
)
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.detection import ClickSignals, classify
from app.models import (
    Campaign,
    Event,
    EventType,
    Target,
    Verdict,
    utcnow,
)
from app.web import client_ip, templates

router = APIRouter()


# A transparent 1x1 PNG, returned by the open-tracking pixel.
_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _seconds_since_send(campaign: Campaign) -> float | None:
    if not campaign or not campaign.sent_at:
        return None
    sent = campaign.sent_at
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=UTC)
    return (utcnow() - sent).total_seconds()


def _log_event(session, target: Target, campaign: Campaign, etype: EventType,
               request: Request, verdict: Verdict, reason: str, secs: float | None) -> None:
    session.add(Event(
        target_id=target.id,
        campaign_id=campaign.id,
        type=etype,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        http_method=request.method,
        verdict=verdict,
        reason=reason,
        seconds_since_send=secs,
    ))
    session.commit()


def _get_target(session, token: str):
    target = session.exec(select(Target).where(Target.token == token)).first()
    if not target:
        return None, None
    campaign = session.get(Campaign, target.campaign_id)
    return target, campaign


@router.get("/t/open/{token}.png")
def track_open(request: Request, token: str):
    with get_session() as session:
        target, campaign = _get_target(session, token)
        if target:
            _log_event(session, target, campaign, EventType.OPEN, request,
                       Verdict.UNKNOWN, "email open (pixel loaded)",
                       _seconds_since_send(campaign))
    return Response(content=_PIXEL, media_type="image/png",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.api_route("/t/click/{token}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def track_click(request: Request, token: str):
    with get_session() as session:
        target, campaign = _get_target(session, token)
        if not target:
            return HTMLResponse("Link expired.", status_code=404)
        secs = _seconds_since_send(campaign)
        result = classify(
            ClickSignals(
                user_agent=request.headers.get("user-agent", ""),
                http_method=request.method,
                seconds_since_send=secs,
                headers={k.lower(): v for k, v in request.headers.items()},
                js_confirmed=False,
                ip=client_ip(request),
            ),
            time_window_seconds=settings.scanner_time_window_seconds,
            scanner_networks=settings.scanner_network_list,
        )
        _log_event(session, target, campaign, EventType.CLICK, request,
                   Verdict(result.verdict), result.reason, secs)
        tok = target.token
    return templates.TemplateResponse(request, "landing.html", {"token": tok})


@router.post("/t/confirm/{token}")
def track_confirm(request: Request, token: str):
    with get_session() as session:
        target, campaign = _get_target(session, token)
        if not target:
            return Response(status_code=404)
        secs = _seconds_since_send(campaign)
        result = classify(
            ClickSignals(user_agent=request.headers.get("user-agent", ""),
                         http_method=request.method, seconds_since_send=secs,
                         headers={k.lower(): v for k, v in request.headers.items()},
                         js_confirmed=True, ip=client_ip(request)),
            time_window_seconds=settings.scanner_time_window_seconds,
            scanner_networks=settings.scanner_network_list,
        )
        _log_event(session, target, campaign, EventType.CONFIRM, request,
                   Verdict(result.verdict), result.reason, secs)
        last_click = session.exec(
            select(Event).where(Event.target_id == target.id,
                                 Event.type == EventType.CLICK)
            .order_by(Event.id.desc())
        ).first()
        if last_click and last_click.verdict != Verdict.HUMAN:
            last_click.verdict = Verdict.HUMAN
            last_click.reason = "confirmed by landing-page JavaScript (interactive browser)"
            session.add(last_click)
            session.commit()
    return Response(status_code=204)


@router.get("/t/report/{token}", response_class=HTMLResponse)
def track_report(request: Request, token: str):
    with get_session() as session:
        target, campaign = _get_target(session, token)
        if not target:
            return HTMLResponse("Link expired.", status_code=404)
        _log_event(session, target, campaign, EventType.REPORT, request,
                   Verdict.HUMAN, "recipient reported the email as phishing",
                   _seconds_since_send(campaign))
    return templates.TemplateResponse(request, "awareness.html",
                                      {"reported": True})
