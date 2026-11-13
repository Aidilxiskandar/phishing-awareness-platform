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
import secrets
from datetime import timezone

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from app.config import settings
from app.database import get_session, init_db
from app.detection import ClickSignals, classify
from app.mailer import send_campaign_email
from app.models import (
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

app = FastAPI(title="Phishing Awareness Platform")
templates = Jinja2Templates(directory="app/templates")

# A transparent 1x1 PNG, returned by the open-tracking pixel.
_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# --- helpers ----------------------------------------------------------------

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _seconds_since_send(campaign: Campaign) -> float | None:
    if not campaign or not campaign.sent_at:
        return None
    sent = campaign.sent_at
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
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


def _risk_scores(session) -> list[dict]:
    """Aggregate each user's behaviour across all campaigns into a risk score.

    human click = +3 (fell for it), open = +1, report = -2 (good habit).
    Scanner clicks are ignored - they are not the person. Higher = riskier.
    """
    users = session.exec(select(User)).all()
    targets = session.exec(select(Target)).all()
    events = session.exec(select(Event)).all()
    targets_by_user: dict[int, list[int]] = {}
    for t in targets:
        targets_by_user.setdefault(t.user_id, []).append(t.id)

    rows = []
    for u in users:
        tids = set(targets_by_user.get(u.id, []))
        ev = [e for e in events if e.target_id in tids]
        opens = sum(1 for e in ev if e.type == EventType.OPEN)
        human_clicks = sum(1 for e in ev if e.type == EventType.CLICK and e.verdict == Verdict.HUMAN)
        reports = sum(1 for e in ev if e.type == EventType.REPORT)
        score = max(0, human_clicks * 3 + opens * 1 - reports * 2)
        band = "High" if score >= 6 else "Medium" if score >= 3 else "Low"
        rows.append({
            "user": u, "campaigns": len(tids), "opens": opens,
            "human_clicks": human_clicks, "reports": reports,
            "score": score, "band": band,
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


# --- Dashboard --------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with get_session() as session:
        users = session.exec(select(User)).all()
        campaigns = session.exec(select(Campaign)).all()
        targets = session.exec(select(Target)).all()
        events = session.exec(select(Event)).all()
        results = session.exec(select(QuizResult)).all()

        sent_targets = len(targets)
        human_clicks = sum(1 for e in events if e.type == EventType.CLICK and e.verdict == Verdict.HUMAN)
        scanner_clicks = sum(1 for e in events if e.type == EventType.CLICK and e.verdict == Verdict.SCANNER)
        reports = sum(1 for e in events if e.type == EventType.REPORT)
        click_rate = (human_clicks / sent_targets * 100) if sent_targets else 0.0

        recent = sorted(events, key=lambda e: e.id or 0, reverse=True)[:10]
        target_by_id = {t.id: t for t in targets}

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
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "tab": "dashboard", "stats": stats,
        "recent": recent, "target_by_id": target_by_id, "dry_run": settings.dry_run,
    })


# --- Phishing (campaigns) ---------------------------------------------------

@app.get("/phishing", response_class=HTMLResponse)
def phishing(request: Request):
    with get_session() as session:
        campaigns = session.exec(select(Campaign).order_by(Campaign.id.desc())).all()
        rows = []
        for c in campaigns:
            targets = session.exec(select(Target).where(Target.campaign_id == c.id)).all()
            events = session.exec(select(Event).where(Event.campaign_id == c.id)).all()
            rows.append({
                "c": c,
                "targets": len(targets),
                "opens": sum(1 for e in events if e.type == EventType.OPEN),
                "human_clicks": sum(1 for e in events if e.type == EventType.CLICK and e.verdict == Verdict.HUMAN),
                "scanner_clicks": sum(1 for e in events if e.type == EventType.CLICK and e.verdict == Verdict.SCANNER),
                "reports": sum(1 for e in events if e.type == EventType.REPORT),
            })
    return templates.TemplateResponse("phishing.html", {
        "request": request, "tab": "phishing", "rows": rows, "dry_run": settings.dry_run,
    })


@app.post("/campaigns")
def create_campaign(name: str = Form(...), subject: str = Form(...),
                    from_name: str = Form(...), from_email: str = Form(...)):
    with get_session() as session:
        c = Campaign(name=name, subject=subject, from_name=from_name, from_email=from_email)
        session.add(c)
        session.commit()
        cid = c.id
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)


@app.get("/campaigns/{cid}", response_class=HTMLResponse)
def campaign_detail(request: Request, cid: int):
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
        all_users = session.exec(select(User).order_by(User.name)).all()
        available = [u for u in all_users if u.id not in targeted_user_ids]
        groups = session.exec(select(StaffGroup).order_by(StaffGroup.name)).all()
    return templates.TemplateResponse("campaign.html", {
        "request": request, "tab": "phishing", "campaign": campaign,
        "targets": targets, "events": events, "target_by_id": target_by_id,
        "available_users": available, "groups": groups, "dry_run": settings.dry_run,
    })


@app.post("/campaigns/{cid}/targets")
def add_targets(cid: int, user_ids: list[int] = Form(default=[])):
    with get_session() as session:
        existing = {t.user_id for t in
                    session.exec(select(Target).where(Target.campaign_id == cid)).all()}
        for uid in user_ids:
            if uid in existing:
                continue
            user = session.get(User, uid)
            if not user:
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
            if not user:
                continue
            session.add(Target(
                campaign_id=cid, user_id=user.id, email=user.email, name=user.name,
                token=secrets.token_urlsafe(16), consented=user.consented,
            ))
        session.commit()
    return RedirectResponse(f"/campaigns/{cid}", status_code=303)


@app.post("/campaigns/{cid}/send")
async def send_campaign(cid: int):
    with get_session() as session:
        campaign = session.get(Campaign, cid)
        if not campaign:
            return HTMLResponse("Campaign not found", status_code=404)
        campaign.sent_at = utcnow()
        campaign.status = CampaignStatus.SENT
        session.add(campaign)
        session.commit()
        campaign_copy = Campaign(**campaign.model_dump())
        targets = session.exec(select(Target).where(Target.campaign_id == cid)).all()
        target_copies = [Target(**t.model_dump()) for t in targets]

    for t in target_copies:
        try:
            await send_campaign_email(campaign_copy, t)
        except PermissionError as e:
            print(f"[skip] {e}")

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


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, group: int | None = None):
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
                select(User).where(User.id.in_(member_ids)).order_by(User.name)
            ).all() if member_ids else []
        else:
            users = session.exec(select(User).order_by(User.id.desc())).all()

        group_rows = [{"g": g, "count": len(members_by_group.get(g.id, set()))} for g in groups]
        active_group = next((g for g in groups if g.id == group), None)
    return templates.TemplateResponse("users.html", {
        "request": request, "tab": "users", "users": users, "groups": groups,
        "group_rows": group_rows, "groups_by_user": groups_by_user,
        "active_group": active_group, "total_users": len(users),
        "dry_run": settings.dry_run,
    })


@app.post("/users")
def add_user(email: str = Form(...), name: str = Form(""),
             department: str = Form(""), consented: str = Form("off")):
    with get_session() as session:
        exists = session.exec(select(User).where(User.email == email)).first()
        if not exists:
            session.add(User(email=email, name=name, department=department,
                             consented=(consented == "on")))
            session.commit()
    return RedirectResponse("/users", status_code=303)


@app.post("/users/seed")
def seed_users(count: int = Form(300)):
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
        import random
        for u in created:
            if random.random() < 0.15:
                session.add(StaffGroupLink(user_id=u.id, group_id=new_staff.id))
            if random.random() < 0.10:
                session.add(StaffGroupLink(user_id=u.id, group_id=failed.id))
        session.commit()
    return RedirectResponse("/users", status_code=303)


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

@app.get("/training", response_class=HTMLResponse)
def training_list(request: Request):
    with get_session() as session:
        modules = session.exec(select(TrainingModule).order_by(TrainingModule.order)).all()
        results = session.exec(select(QuizResult).order_by(QuizResult.id.desc())).all()
        module_by_id = {m.id: m for m in modules}
        done = len(results)
        passed = sum(1 for r in results if r.total and r.score == r.total)
    return templates.TemplateResponse("training_list.html", {
        "request": request, "tab": "training", "modules": modules, "results": results[:15],
        "module_by_id": module_by_id, "done": done, "passed": passed, "dry_run": settings.dry_run,
    })


@app.get("/training/{slug}", response_class=HTMLResponse)
def training_detail(request: Request, slug: str, token: str = ""):
    with get_session() as session:
        module = session.exec(select(TrainingModule).where(TrainingModule.slug == slug)).first()
        if not module:
            return HTMLResponse("Module not found", status_code=404)
        questions = session.exec(
            select(TrainingQuestion).where(TrainingQuestion.module_id == module.id)
            .order_by(TrainingQuestion.order)
        ).all()
        bullets = [b for b in module.body.split("\n") if b.strip()]
    return templates.TemplateResponse("training_detail.html", {
        "request": request, "tab": "training", "module": module, "questions": questions,
        "bullets": bullets, "token": token, "result": None, "dry_run": settings.dry_run,
    })


@app.post("/training/{slug}/quiz", response_class=HTMLResponse)
async def submit_quiz(request: Request, slug: str):
    form = await request.form()
    token = form.get("token", "")
    with get_session() as session:
        module = session.exec(select(TrainingModule).where(TrainingModule.slug == slug)).first()
        if not module:
            return HTMLResponse("Module not found", status_code=404)
        questions = session.exec(
            select(TrainingQuestion).where(TrainingQuestion.module_id == module.id)
            .order_by(TrainingQuestion.order)
        ).all()
        score = 0
        for q in questions:
            answer = form.get(f"q{q.id}")
            if answer is not None and answer.isdigit() and int(answer) == q.correct_index:
                score += 1
        user_id = None
        if token:
            target = session.exec(select(Target).where(Target.token == token)).first()
            if target:
                user_id = target.user_id
        session.add(QuizResult(module_id=module.id, token=token, user_id=user_id,
                               score=score, total=len(questions)))
        session.commit()
        bullets = [b for b in module.body.split("\n") if b.strip()]
        result = {"score": score, "total": len(questions)}
    return templates.TemplateResponse("training_detail.html", {
        "request": request, "tab": "training", "module": module, "questions": questions,
        "bullets": bullets, "token": token, "result": result, "dry_run": settings.dry_run,
    })


# --- Reports ----------------------------------------------------------------

@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request):
    with get_session() as session:
        risk = _risk_scores(session)
        events = session.exec(select(Event).order_by(Event.id.desc())).all()
        targets = session.exec(select(Target)).all()
        campaigns = session.exec(select(Campaign)).all()
        target_by_id = {t.id: t for t in targets}
        campaign_by_id = {c.id: c for c in campaigns}
    return templates.TemplateResponse("reports.html", {
        "request": request, "tab": "reports", "risk": risk, "events": events[:200],
        "target_by_id": target_by_id, "campaign_by_id": campaign_by_id, "dry_run": settings.dry_run,
    })


@app.get("/reports/export.csv")
def export_csv():
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
        w.writerow([
            e.created_at.isoformat(),
            c.name if c else e.campaign_id,
            t.email if t else e.target_id,
            e.type.value, e.verdict.value, e.reason, e.ip, e.user_agent,
            e.http_method,
            f"{e.seconds_since_send:.1f}" if e.seconds_since_send is not None else "",
        ])
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
    return templates.TemplateResponse("landing.html", {"request": request, "token": tok})


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
    return templates.TemplateResponse("awareness.html",
                                      {"request": request, "reported": True})
