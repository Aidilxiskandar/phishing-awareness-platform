"""Users tab: the staff directory, consent, groups, seeding and right-to-erasure."""
from __future__ import annotations

import random
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.models import (
    StaffGroup,
    StaffGroupLink,
    User,
)
from app.sampledata import generate_staff
from app.services.erasure import erase_user
from app.web import record_audit, templates

router = APIRouter()


# Pragmatic email check (not full RFC 5322): one @, a dotted domain, no spaces.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


@router.get("/users", response_class=HTMLResponse)
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


@router.post("/users")
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
            record_audit(request, "user.add", f"{email} consented={consented == 'on'}")
    return RedirectResponse("/users", status_code=303)


@router.post("/users/seed")
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
    record_audit(request, "users.seed", f"generated {count} staff")
    return RedirectResponse("/users", status_code=303)


@router.post("/users/{uid}/erase")
def erase_user_route(request: Request, uid: int):
    """Right to erasure: anonymise the person and scrub their PII everywhere."""
    with get_session() as session:
        counts = erase_user(session, uid)
    if counts is None:
        return RedirectResponse("/users?error=not_found", status_code=303)
    # Log the id only: recording the email here would undo the erasure.
    record_audit(request, "user.erase",
                  f"user #{uid} erased ({counts['targets']} target(s), "
                  f"{counts['events']} event(s) scrubbed)")
    return RedirectResponse("/users?notice=erased", status_code=303)


@router.post("/groups")
def create_group(name: str = Form(...), description: str = Form("")):
    name = name.strip()
    if name:
        with get_session() as session:
            _get_or_create_group(session, name, description.strip())
    return RedirectResponse("/users", status_code=303)


@router.post("/users/assign")
def assign_to_group(group_id: int = Form(...), user_ids: list[int] = Form(default=[])):
    with get_session() as session:
        existing = {(ln.user_id, ln.group_id) for ln in session.exec(select(StaffGroupLink)).all()}
        for uid in user_ids:
            if (uid, group_id) not in existing:
                session.add(StaffGroupLink(user_id=uid, group_id=group_id))
        session.commit()
    return RedirectResponse("/users", status_code=303)
