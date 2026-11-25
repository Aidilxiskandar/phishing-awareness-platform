"""Recipient-facing tracking endpoints (public, hit by email clients and the landing page).

  GET  /t/open/{token}.png    1x1 pixel -> logs an OPEN
  GET/HEAD /t/click/{token}   tracked link -> logs a CLICK, classifies, shows landing page
  POST /t/confirm/{token}     JS beacon from landing page -> logs CONFIRM, upgrades to HUMAN
  GET/HEAD /t/report/{token}  "Report this email" confirmation page; records NOTHING
                              (mail scanners fetch every link in a message)
  POST /t/report/{token}      the page's JS or button press -> report recorded once
"""
from __future__ import annotations

import base64
from datetime import UTC

from fastapi import APIRouter, Form, Request
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
from app.services.reporting import record_report
from app.web import client_ip, logger, templates

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
        # Only a confirm that is itself human may upgrade the click. A detonation
        # sandbox runs the beacon JS too, but announces itself (headless UA,
        # automation headers, scanner network), so its confirm is a scanner and
        # must never turn the click into a human one.
        if (result.verdict == Verdict.HUMAN.value and last_click
                and last_click.verdict != Verdict.HUMAN):
            last_click.verdict = Verdict.HUMAN
            last_click.reason = "confirmed by landing-page JavaScript (interactive browser)"
            session.add(last_click)
            session.commit()
    return Response(status_code=204)


def _report_thanks(request: Request, already: bool):
    return templates.TemplateResponse(request, "awareness.html",
                                      {"reported": True, "already": already})


@router.api_route("/t/report/{token}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def report_page(request: Request, token: str):
    with get_session() as session:
        target, _ = _get_target(session, token)
        if not target:
            return HTMLResponse("Link expired.", status_code=404)
        if target.reported_at is not None:
            return _report_thanks(request, already=True)
    logger.info("report_link_fetched target=%s ua=%r method=%s", target.id,
                request.headers.get("user-agent", "")[:80], request.method)
    return templates.TemplateResponse(request, "report_confirm.html", {"token": token})


@router.post("/t/report/{token}", response_class=HTMLResponse)
def report_submit(request: Request, token: str, js: str = Form("0")):
    with get_session() as session:
        target, campaign = _get_target(session, token)
        if not target:
            return HTMLResponse("Link expired.", status_code=404)
        outcome = record_report(
            session, target, campaign,
            user_agent=request.headers.get("user-agent", ""),
            http_method=request.method,
            headers={k.lower(): v for k, v in request.headers.items()},
            js_confirmed=(js == "1"), ip=client_ip(request),
            time_window_seconds=settings.scanner_time_window_seconds,
            scanner_networks=settings.scanner_network_list,
        )
    if outcome.counted or outcome.already:
        return _report_thanks(request, already=outcome.already)
    logger.info("report_rejected target=%s reason=%s", target.id, outcome.reason)
    # No auto-submit on the re-rendered page: an automated client that runs JS
    # (a detonation sandbox) would otherwise POST in an endless loop.
    return templates.TemplateResponse(request, "report_confirm.html",
                                      {"token": token, "rejected": True}, status_code=202)
