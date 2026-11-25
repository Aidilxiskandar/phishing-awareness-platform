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

import base64
import csv
import io
import logging
import random
import re
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from app import security
from app.config import settings
from app.database import get_session, init_db
from app.detection import ClickSignals, classify
from app.mailer import build_tracking_urls, render_email_html, send_campaign_email
from app.models import (
    AuditLog,
    Campaign,
    CampaignStatus,
    Event,
    EventType,
    QuizResult,
    StaffGroup,
    StaffGroupLink,
    Target,
    TrainingModule,
    TrainingQuestion,
    User,
    Verdict,
    utcnow,
)
from app.sampledata import generate_staff
from app.services.charts import donut as _donut
from app.services.charts import trend as _trend
from app.services.email_templates import TEMPLATES as EMAIL_TEMPLATES
from app.services.email_templates import get_template as get_email_template
from app.services.erasure import erase_user
from app.services.risk import risk_scores as _risk_scores
from app.services.video import video_info as _video_info

logger = logging.getLogger("phishguard")

# Pragmatic email check (not full RFC 5322): one @, a dotted domain, no spaces.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _record_audit(request: Request, action: str, detail: str = "") -> None:
    """Append an audit entry for a privileged admin action (best-effort)."""
    try:
        actor = request.session.get("admin", "?")
    except (AssertionError, KeyError):
        actor = "?"
    try:
        with get_session() as session:
            session.add(AuditLog(actor=actor, action=action,
                                 detail=detail[:300], ip=_client_ip(request)))
            session.commit()
        logger.info("audit action=%s actor=%s detail=%s", action, actor, detail[:120])
    except Exception:
        logger.exception("audit write failed for action=%s", action)


def _csv_safe(value) -> str:
    """Neutralise CSV formula injection: a cell starting with = + - @ (or a tab/CR
    before them) is executed by spreadsheet apps, so prefix it with a quote."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


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

# Templates live next to this module; resolve absolutely so the app works from
# any working directory.
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


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


# --- Auth & health routes ----------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {
        "next": security.safe_next(next), "error": None,
        "tab": None, "dry_run": settings.dry_run,
    })


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...),
          next: str = Form("/")):
    ip = _client_ip(request)

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
    _record_audit(request, "login", f"admin '{username}' signed in")
    return RedirectResponse(security.safe_next(next), status_code=303)


@app.post("/logout")
def logout(request: Request):
    if security.is_authenticated(request):
        _record_audit(request, "logout", "admin signed out")
    security.end_session(request)
    return RedirectResponse("/login", status_code=303)


@app.get("/health")
def health():
    """Liveness/readiness probe: confirms the app and DB respond."""
    try:
        with get_session() as session:
            session.exec(select(User.id).limit(1)).all()
        return {"status": "ok"}
    except Exception:
        return JSONResponse({"status": "degraded"}, status_code=503)


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

# A transparent 1x1 PNG, returned by the open-tracking pixel.
_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


# --- helpers ----------------------------------------------------------------

def _client_ip(request: Request) -> str:
    """Client IP for the evidence log (see security.client_ip: X-Forwarded-For is
    only honoured from TRUSTED_PROXIES, walked right-to-left, so a client can't
    forge the address written into the evidence)."""
    return security.client_ip(request)


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
        ip=_client_ip(request),
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


# --- Dashboard --------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
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


# --- Phishing (campaigns) ---------------------------------------------------

@app.get("/phishing", response_class=HTMLResponse)
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


@app.post("/campaigns")
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
    _record_audit(request, "campaign.create", f"#{cid} '{name}' template={template_slug or 'custom'}")
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)


@app.get("/campaigns/{cid}", response_class=HTMLResponse)
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


@app.get("/campaigns/{cid}/preview/{tid}", response_class=HTMLResponse)
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


@app.get("/campaigns/{cid}/email/{tid}", response_class=HTMLResponse)
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


@app.get("/templates/{slug}/preview", response_class=HTMLResponse)
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


@app.get("/templates/{slug}/email", response_class=HTMLResponse)
def template_email(slug: str):
    """Raw rendered email HTML for a template preview iframe (no tracking fired)."""
    tmpl = get_email_template(slug)
    if not tmpl:
        return HTMLResponse("Not found", status_code=404)
    campaign, target = _preview_pair(tmpl)
    return HTMLResponse(render_email_html(campaign, target, preview=True))


@app.post("/campaigns/{cid}/targets")
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


@app.post("/campaigns/{cid}/targets_group")
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


@app.post("/campaigns/{cid}/send")
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

    _record_audit(request, "campaign.send", f"#{cid} to {n_targets} target(s)")
    background_tasks.add_task(_run_campaign_send, cid)
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)


# --- Users ------------------------------------------------------------------

def _get_or_create_group(session, name: str, description: str = "") -> StaffGroup:
    g = session.exec(select(StaffGroup).where(StaffGroup.name == name)).first()
    if g:
        return g
    g = StaffGroup(name=name, description=description)
    session.add(g)
    session.commit()
    return g


_USERS_NOTICES = {
    "erased": "Personal data erased. The person is now an anonymous placeholder "
              "and old tracking links no longer work.",
    "not_found": "That user no longer exists.",
    "invalid_email": "That doesn't look like a valid email address.",
}


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, group: int | None = None, notice: str = "",
               error: str = ""):
    with get_session() as session:
        groups = session.exec(select(StaffGroup).order_by(StaffGroup.name)).all()
        links = session.exec(select(StaffGroupLink)).all()

        # membership maps
        group_name = {g.id: g.name for g in groups}
        groups_by_user: dict[int, list[str]] = {}
        members_by_group: dict[int, set[int]] = {}
        for ln in links:
            groups_by_user.setdefault(ln.user_id, []).append(group_name.get(ln.group_id, "?"))
            members_by_group.setdefault(ln.group_id, set()).add(ln.user_id)

        if group:
            member_ids = members_by_group.get(group, set())
            users = session.exec(
                select(User).where(User.id.in_(member_ids), User.erased_at.is_(None))
                .order_by(User.name)
            ).all() if member_ids else []
        else:
            users = session.exec(
                select(User).where(User.erased_at.is_(None)).order_by(User.id.desc())
            ).all()

        group_rows = [{"g": g, "count": len(members_by_group.get(g.id, set()))} for g in groups]
        active_group = next((g for g in groups if g.id == group), None)
    return templates.TemplateResponse(request, "users.html", {
        "tab": "users", "users": users, "groups": groups,
        "group_rows": group_rows, "groups_by_user": groups_by_user,
        "active_group": active_group, "total_users": len(users),
        "notice": _USERS_NOTICES.get(notice or error, ""),
        "dry_run": settings.dry_run,
    })


@app.post("/users")
def add_user(request: Request, email: str = Form(...), name: str = Form(""),
             department: str = Form(""), consented: str = Form("off")):
    email = email.strip()
    if not _EMAIL_RE.match(email):
        return RedirectResponse("/users?error=invalid_email", status_code=303)
    with get_session() as session:
        exists = session.exec(select(User).where(User.email == email)).first()
        if not exists:
            session.add(User(email=email, name=name[:120], department=department[:120],
                             consented=(consented == "on")))
            session.commit()
            _record_audit(request, "user.add", f"{email} consented={consented == 'on'}")
    return RedirectResponse("/users", status_code=303)


@app.post("/users/seed")
def seed_users(request: Request, count: int = Form(300)):
    count = max(1, min(count, 2000))  # sane bounds
    with get_session() as session:
        existing = {u.email for u in session.exec(select(User)).all()}
        new_users = generate_staff(count, existing)
        created: list[User] = []
        for d in new_users:
            u = User(**d)
            session.add(u)
            created.append(u)
        session.commit()

        # Demonstrate grouping: drop a random slice into two example groups.
        new_staff = _get_or_create_group(session, "New staff",
                                         "Joined recently - prioritise for awareness training.")
        failed = _get_or_create_group(session, "Failed phishing - this month",
                                      "Clicked a simulated phish and need a follow-up.")
        for u in created:
            if random.random() < 0.15:
                session.add(StaffGroupLink(user_id=u.id, group_id=new_staff.id))
            if random.random() < 0.10:
                session.add(StaffGroupLink(user_id=u.id, group_id=failed.id))
        session.commit()
    _record_audit(request, "users.seed", f"generated {count} staff")
    return RedirectResponse("/users", status_code=303)


@app.post("/users/{uid}/erase")
def erase_user_route(request: Request, uid: int):
    """Right to erasure: anonymise the person and scrub their PII everywhere."""
    with get_session() as session:
        counts = erase_user(session, uid)
    if counts is None:
        return RedirectResponse("/users?error=not_found", status_code=303)
    # Log the id only: recording the email here would undo the erasure.
    _record_audit(request, "user.erase",
                  f"user #{uid} erased ({counts['targets']} target(s), "
                  f"{counts['events']} event(s) scrubbed)")
    return RedirectResponse("/users?notice=erased", status_code=303)


@app.post("/groups")
def create_group(name: str = Form(...), description: str = Form("")):
    name = name.strip()
    if name:
        with get_session() as session:
            _get_or_create_group(session, name, description.strip())
    return RedirectResponse("/users", status_code=303)


@app.post("/users/assign")
def assign_to_group(group_id: int = Form(...), user_ids: list[int] = Form(default=[])):
    with get_session() as session:
        existing = {(ln.user_id, ln.group_id) for ln in session.exec(select(StaffGroupLink)).all()}
        for uid in user_ids:
            if (uid, group_id) not in existing:
                session.add(StaffGroupLink(user_id=uid, group_id=group_id))
        session.commit()
    return RedirectResponse("/users", status_code=303)


# --- Training ---------------------------------------------------------------

def _passed(score: int, total: int) -> bool:
    """A quiz attempt passes when it meets the configured pass mark."""
    return bool(total) and score * 100 >= settings.training_pass_percent * total


@app.get("/training", response_class=HTMLResponse)
def training_list(request: Request):
    with get_session() as session:
        modules = session.exec(select(TrainingModule).order_by(TrainingModule.order)).all()
        results = session.exec(select(QuizResult).order_by(QuizResult.id.desc())).all()
        module_by_id = {m.id: m for m in modules}
        done = len(results)
        passed = sum(1 for r in results if _passed(r.score, r.total))
        # Per-module pass counts, and per-person progress (attempts linked via token).
        module_passes: dict[int, set] = {m.id: set() for m in modules}
        person_passed: dict[int, set] = {}
        person_tried: dict[int, set] = {}
        for r in results:
            key = r.user_id if r.user_id is not None else f"anon-{r.id}"
            if _passed(r.score, r.total) and r.module_id in module_passes:
                module_passes[r.module_id].add(key)
            if r.user_id is not None:
                person_tried.setdefault(r.user_id, set()).add(r.module_id)
                if _passed(r.score, r.total):
                    person_passed.setdefault(r.user_id, set()).add(r.module_id)
        users = {u.id: u for u in session.exec(
            select(User).where(User.id.in_(list(person_tried)), User.erased_at.is_(None))).all()} if person_tried else {}
        module_ids = set(module_by_id)
        progress = sorted(
            ({"user": users[uid],
              "passed": len(person_passed.get(uid, set()) & module_ids),
              "tried": len(tried & module_ids)}
             for uid, tried in person_tried.items() if uid in users),
            key=lambda row: (-row["passed"], row["user"].email),
        )
    return templates.TemplateResponse(request, "training_list.html", {
        "tab": "training", "modules": modules, "results": results[:15],
        "module_by_id": module_by_id, "done": done, "passed": passed,
        "module_passes": {mid: len(v) for mid, v in module_passes.items()},
        "progress": progress, "pass_percent": settings.training_pass_percent,
        "passed_fn": _passed, "dry_run": settings.dry_run,
    })


def _training_page(request: Request, slug: str, *, target: Target | None,
                   form=None):
    """Render a training module, and grade + record its quiz when `form` is given.

    Two audiences share this page:
      * admins preview modules at /training/{slug} (inside the admin app);
      * staff arrive from a drill's landing page at /t/training/{token}/{slug}.
        That path is public (recipients have no admin login), so it only works
        with a real drill token and never shows admin navigation.
    """
    staff = target is not None
    token = target.token if staff else ""
    with get_session() as session:
        module = session.exec(select(TrainingModule).where(TrainingModule.slug == slug)).first()
        if not module:
            return HTMLResponse("Module not found", status_code=404)
        questions = session.exec(
            select(TrainingQuestion).where(TrainingQuestion.module_id == module.id)
            .order_by(TrainingQuestion.order)
        ).all()
        result = None
        if form is not None:
            score = 0
            for q in questions:
                answer = form.get(f"q{q.id}")
                if isinstance(answer, str) and answer.isdigit() and int(answer) == q.correct_index:
                    score += 1
            session.add(QuizResult(module_id=module.id, token=token,
                                   user_id=target.user_id if staff else None,
                                   score=score, total=len(questions)))
            session.commit()
            result = {"score": score, "total": len(questions),
                      "passed": _passed(score, len(questions)),
                      "pass_percent": settings.training_pass_percent}
        bullets = [b for b in module.body.split("\n") if b.strip()]
        video = _video_info(module)
    base = f"/t/training/{token}" if staff else "/training"
    return templates.TemplateResponse(request, "training_detail.html", {
        "tab": "training", "module": module, "questions": questions,
        "bullets": bullets, "video": video, "result": result,
        "staff": staff, "train_base": base, "dry_run": settings.dry_run,
    })


def _find_target(token: str) -> Target | None:
    with get_session() as session:
        return session.exec(select(Target).where(Target.token == token)).first()


@app.get("/training/{slug}", response_class=HTMLResponse)
def training_detail(request: Request, slug: str):
    return _training_page(request, slug, target=None)


@app.post("/training/{slug}/quiz", response_class=HTMLResponse)
async def submit_quiz(request: Request, slug: str):
    return _training_page(request, slug, target=None, form=await request.form())


@app.get("/t/training/{token}/{slug}", response_class=HTMLResponse)
def staff_training(request: Request, token: str, slug: str):
    target = _find_target(token)
    if not target:
        return HTMLResponse("This training link is not valid.", status_code=404)
    return _training_page(request, slug, target=target)


@app.post("/t/training/{token}/{slug}/quiz", response_class=HTMLResponse)
async def staff_submit_quiz(request: Request, token: str, slug: str):
    target = _find_target(token)
    if not target:
        return HTMLResponse("This training link is not valid.", status_code=404)
    return _training_page(request, slug, target=target, form=await request.form())


# --- Reports ----------------------------------------------------------------

@app.get("/reports", response_class=HTMLResponse)
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
    return templates.TemplateResponse(request, "reports.html", {
        "tab": "reports", "risk": risk, "events": events, "audit": audit,
        "target_by_id": target_by_id, "campaign_by_id": campaign_by_id, "dry_run": settings.dry_run,
    })


@app.get("/reports/export.csv")
def export_csv(request: Request):
    _record_audit(request, "users.export", "evidence CSV downloaded")
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


# --- tracking endpoints ------------------------------------------------------

@app.get("/t/open/{token}.png")
def track_open(request: Request, token: str):
    with get_session() as session:
        target, campaign = _get_target(session, token)
        if target:
            _log_event(session, target, campaign, EventType.OPEN, request,
                       Verdict.UNKNOWN, "email open (pixel loaded)",
                       _seconds_since_send(campaign))
    return Response(content=_PIXEL, media_type="image/png",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.api_route("/t/click/{token}", methods=["GET", "HEAD"], response_class=HTMLResponse)
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
            ),
            time_window_seconds=settings.scanner_time_window_seconds,
        )
        _log_event(session, target, campaign, EventType.CLICK, request,
                   Verdict(result.verdict), result.reason, secs)
        tok = target.token
    return templates.TemplateResponse(request, "landing.html", {"token": tok})


@app.post("/t/confirm/{token}")
def track_confirm(request: Request, token: str):
    with get_session() as session:
        target, campaign = _get_target(session, token)
        if not target:
            return Response(status_code=404)
        secs = _seconds_since_send(campaign)
        result = classify(
            ClickSignals(user_agent=request.headers.get("user-agent", ""),
                         http_method=request.method, seconds_since_send=secs,
                         js_confirmed=True),
            time_window_seconds=settings.scanner_time_window_seconds,
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


@app.get("/t/report/{token}", response_class=HTMLResponse)
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
