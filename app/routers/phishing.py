"""Phishing tab: campaigns, drill-template previews, targeting and sending."""
from __future__ import annotations

import secrets
from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from sqlalchemy import func
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.mailer import build_tracking_urls, render_email_html, send_campaign_email
from app.models import (
    Campaign,
    CampaignStatus,
    Event,
    EventType,
    StaffGroup,
    StaffGroupLink,
    Target,
    User,
    Verdict,
    utcnow,
)
from app.services.email_templates import TEMPLATES as EMAIL_TEMPLATES
from app.services.email_templates import get_template as get_email_template
from app.web import logger, record_audit, templates

router = APIRouter()


@router.get("/phishing", response_class=HTMLResponse)
def phishing(request: Request):
    with get_session() as session:
        campaigns = session.exec(select(Campaign).order_by(Campaign.id.desc())).all()
        # Grouped counts instead of two queries per campaign (N+1).
        target_counts = dict(session.exec(
            select(Target.campaign_id, func.count()).group_by(Target.campaign_id)
        ).all())
        opens: Counter[int] = Counter()
        human: Counter[int] = Counter()
        scanner: Counter[int] = Counter()
        reports: Counter[int] = Counter()
        agg = session.exec(
            select(Event.campaign_id, Event.type, Event.verdict, func.count())
            .group_by(Event.campaign_id, Event.type, Event.verdict)
        ).all()
        for cid, etype, verdict, n in agg:
            if etype == EventType.OPEN:
                opens[cid] += n
            elif etype == EventType.CLICK and verdict == Verdict.HUMAN:
                human[cid] += n
            elif etype == EventType.CLICK and verdict == Verdict.SCANNER:
                scanner[cid] += n
            elif etype == EventType.REPORT:
                reports[cid] += n
        rows = [{
            "c": c, "targets": target_counts.get(c.id, 0), "opens": opens[c.id],
            "human_clicks": human[c.id], "scanner_clicks": scanner[c.id],
            "reports": reports[c.id],
        } for c in campaigns]
    return templates.TemplateResponse(request, "phishing.html", {
        "tab": "phishing", "rows": rows, "email_templates": EMAIL_TEMPLATES,
        "dry_run": settings.dry_run,
    })


@router.post("/campaigns")
def create_campaign(request: Request, name: str = Form(...), subject: str = Form(...),
                    from_name: str = Form(...), from_email: str = Form(...),
                    template_slug: str = Form(""), body: str = Form("")):
    # A template seeds the sender/subject/body/CTA and snapshots its red flags so
    # the teaching points survive later library changes. The admin can still
    # override the subject and body (kept custom), so a custom drill is allowed.
    tmpl = get_email_template(template_slug) if template_slug else None
    cta_label = tmpl.cta_label if tmpl else ""
    red_flags_json = tmpl.red_flags_json if tmpl else "[]"
    body = body.strip() or (tmpl.body if tmpl else "")
    with get_session() as session:
        c = Campaign(name=name, subject=subject, from_name=from_name, from_email=from_email,
                     template_slug=template_slug, body=body, cta_label=cta_label,
                     red_flags_json=red_flags_json)
        session.add(c)
        session.commit()
        cid = c.id
    record_audit(request, "campaign.create", f"#{cid} '{name}' template={template_slug or 'custom'}")
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)


@router.get("/campaigns/{cid}", response_class=HTMLResponse)
def campaign_detail(request: Request, cid: int, notice: str = ""):
    with get_session() as session:
        campaign = session.get(Campaign, cid)
        if not campaign:
            return HTMLResponse("Campaign not found", status_code=404)
        targets = session.exec(select(Target).where(Target.campaign_id == cid)).all()
        events = session.exec(
            select(Event).where(Event.campaign_id == cid).order_by(Event.id.desc())
        ).all()
        target_by_id = {t.id: t for t in targets}
        targeted_user_ids = {t.user_id for t in targets}
        all_users = session.exec(
            select(User).where(User.erased_at.is_(None)).order_by(User.name)).all()
        available = [u for u in all_users if u.id not in targeted_user_ids]
        groups = session.exec(select(StaffGroup).order_by(StaffGroup.name)).all()
    notice_text = {
        "already_sent": "This campaign has already been sent — re-sending is blocked.",
    }.get(notice, "")
    return templates.TemplateResponse(request, "campaign.html", {
        "tab": "phishing", "campaign": campaign,
        "targets": targets, "events": events, "target_by_id": target_by_id,
        "available_users": available, "groups": groups, "notice": notice_text,
        "dry_run": settings.dry_run,
    })


@router.get("/campaigns/{cid}/preview/{tid}", response_class=HTMLResponse)
def preview_email(request: Request, cid: int, tid: int):
    """Admin view: the exact personalised email this recipient received,
    shown in an email-client style frame. Tracking is neutralised in preview."""
    with get_session() as session:
        campaign = session.get(Campaign, cid)
        target = session.get(Target, tid)
        if not campaign or not target or target.campaign_id != cid:
            return HTMLResponse("Not found", status_code=404)
        urls = build_tracking_urls(target.token)
    return templates.TemplateResponse(request, "email_preview.html", {
        "tab": "phishing", "campaign": campaign,
        "target": target, "urls": urls, "red_flags": campaign.red_flags,
        "dry_run": settings.dry_run,
    })


@router.get("/campaigns/{cid}/email/{tid}", response_class=HTMLResponse)
def raw_email(cid: int, tid: int):
    """Raw rendered email HTML for the preview iframe (no tracking fired)."""
    with get_session() as session:
        campaign = session.get(Campaign, cid)
        target = session.get(Target, tid)
        if not campaign or not target or target.campaign_id != cid:
            return HTMLResponse("Not found", status_code=404)
        html = render_email_html(campaign, target, preview=True)
    return HTMLResponse(html)


def _preview_pair(tmpl):
    """An unsaved Campaign + Target built from a library template, for previewing
    a drill before any campaign exists. Never persisted; the token is a placeholder."""
    campaign = Campaign(name=tmpl.name, from_name=tmpl.from_name, from_email=tmpl.from_email,
                        subject=tmpl.subject, body=tmpl.body, cta_label=tmpl.cta_label,
                        template_slug=tmpl.slug, red_flags_json=tmpl.red_flags_json)
    target = Target(campaign_id=0, user_id=0, email="recipient@example.com",
                    name="Sam Taylor", token="preview")
    return campaign, target


@router.get("/templates/{slug}/preview", response_class=HTMLResponse)
def preview_template(request: Request, slug: str):
    """Preview a library template before creating a campaign (reuses email_preview.html)."""
    tmpl = get_email_template(slug)
    if not tmpl:
        return HTMLResponse("Template not found", status_code=404)
    campaign, target = _preview_pair(tmpl)
    return templates.TemplateResponse(request, "email_preview.html", {
        "tab": "phishing", "campaign": campaign, "target": target,
        "urls": build_tracking_urls(target.token), "red_flags": tmpl.red_flags,
        "email_url": f"/templates/{slug}/email", "dry_run": settings.dry_run,
    })


@router.get("/templates/{slug}/email", response_class=HTMLResponse)
def template_email(slug: str):
    """Raw rendered email HTML for a template preview iframe (no tracking fired)."""
    tmpl = get_email_template(slug)
    if not tmpl:
        return HTMLResponse("Not found", status_code=404)
    campaign, target = _preview_pair(tmpl)
    return HTMLResponse(render_email_html(campaign, target, preview=True))


@router.post("/campaigns/{cid}/targets")
def add_targets(cid: int, user_ids: list[int] = Form(default=[])):
    with get_session() as session:
        existing = {t.user_id for t in
                    session.exec(select(Target).where(Target.campaign_id == cid)).all()}
        for uid in user_ids:
            if uid in existing:
                continue
            user = session.get(User, uid)
            if not user or user.erased_at:
                continue
            session.add(Target(
                campaign_id=cid, user_id=user.id, email=user.email, name=user.name,
                token=secrets.token_urlsafe(16), consented=user.consented,
            ))
        session.commit()
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)


@router.post("/campaigns/{cid}/targets_group")
def add_group_targets(cid: int, group_id: int = Form(...)):
    with get_session() as session:
        existing = {t.user_id for t in
                    session.exec(select(Target).where(Target.campaign_id == cid)).all()}
        member_ids = [ln.user_id for ln in
                      session.exec(select(StaffGroupLink).where(StaffGroupLink.group_id == group_id)).all()]
        for uid in member_ids:
            if uid in existing:
                continue
            user = session.get(User, uid)
            if not user or user.erased_at:
                continue
            session.add(Target(
                campaign_id=cid, user_id=user.id, email=user.email, name=user.name,
                token=secrets.token_urlsafe(16), consented=user.consented,
            ))
        session.commit()
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)


async def _run_campaign_send(cid: int) -> None:
    """Send a campaign's un-sent targets, one at a time, recording per-target state.

    Runs as a background task so the HTTP request returns immediately. Safe to
    resume: only targets without a sent_at are attempted, each wrapped so one
    failure never aborts the batch. Consent is re-checked LIVE here (not from the
    stale snapshot), so revoking a user's consent before send still protects them.
    """
    allowed = settings.allowed_domains
    with get_session() as session:
        campaign = session.get(Campaign, cid)
        if not campaign:
            return
        targets = session.exec(
            select(Target).where(Target.campaign_id == cid, Target.sent_at.is_(None))
        ).all()
        for t in targets:
            user = session.get(User, t.user_id)
            live_consent = bool(t.consented and user and user.consented)
            if not live_consent:
                t.send_error = "skipped: recipient is not marked as consenting"
                session.add(t)
                session.commit()
                continue
            if allowed and t.email.rsplit("@", 1)[-1].lower() not in allowed:
                t.send_error = "skipped: recipient domain not in allowlist"
                session.add(t)
                session.commit()
                continue
            try:
                await send_campaign_email(campaign, t)
                t.sent_at = utcnow()
                t.send_error = ""
            except Exception as exc:  # noqa: BLE001 - record any send failure per target
                t.send_error = str(exc)[:500]
                logger.warning("send failed for target %s (%s): %s", t.id, t.email, exc)
            session.add(t)
            session.commit()

        campaign.status = CampaignStatus.SENT
        session.add(campaign)
        session.commit()


@router.post("/campaigns/{cid}/send")
def send_campaign(request: Request, cid: int, background_tasks: BackgroundTasks):
    with get_session() as session:
        campaign = session.get(Campaign, cid)
        if not campaign:
            return HTMLResponse("Campaign not found", status_code=404)
        # Idempotency guard: never re-send a campaign that is already sent/sending.
        if campaign.status in (CampaignStatus.SENT, CampaignStatus.SENDING):
            return RedirectResponse(f"/campaigns/{cid}?notice=already_sent", status_code=303)
        campaign.status = CampaignStatus.SENDING
        campaign.sent_at = utcnow()
        session.add(campaign)
        session.commit()
        n_targets = len(session.exec(select(Target).where(Target.campaign_id == cid)).all())

    record_audit(request, "campaign.send", f"#{cid} to {n_targets} target(s)")
    background_tasks.add_task(_run_campaign_send, cid)
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)
