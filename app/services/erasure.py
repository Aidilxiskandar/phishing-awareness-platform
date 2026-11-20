"""Right to erasure (GDPR Art. 17 / PDPA withdrawal of consent).

Erasing a person *anonymises* them in place rather than hard-deleting rows, so
campaign-level aggregates (sent / opened / clicked counts) stay accurate while
nothing that identifies the person remains:

  User         email -> unique placeholder, name/department blanked, consent
               revoked, erased_at stamped, removed from every group.
  Target       email/name snapshots replaced; tracking token rotated so links in
               already-delivered emails stop resolving (no further collection).
  Event        IP address and user-agent wiped (behavioural type/verdict kept).
  QuizResult   unlinked from the user and their token.
  AuditLog     any mention of the email in earlier entries is redacted.
"""
from __future__ import annotations

import secrets

from sqlmodel import Session, select

from app.models import AuditLog, Event, QuizResult, StaffGroupLink, Target, User, utcnow

REDACTED = "[erased]"


def placeholder_email(user_id: int) -> str:
    # .invalid is reserved (RFC 2606): it can never be a deliverable address.
    return f"erased-{user_id}@erased.invalid"


def erase_user(session: Session, user_id: int) -> dict[str, int] | None:
    """Anonymise one user and everything linked to them.

    Returns per-table counts of rows touched, or None if the user doesn't exist.
    Idempotent: erasing an already-erased user is a harmless no-op re-scrub.
    """
    user = session.get(User, user_id)
    if user is None:
        return None

    original_email = user.email
    already_erased = user.erased_at is not None

    targets = session.exec(select(Target).where(Target.user_id == user_id)).all()
    target_ids = [t.id for t in targets]
    tokens = [t.token for t in targets if t.token]

    # Events: drop the network fingerprint, keep what happened for aggregates.
    events = session.exec(select(Event).where(Event.target_id.in_(target_ids))).all() \
        if target_ids else []
    for e in events:
        e.ip = ""
        e.user_agent = ""
        session.add(e)

    # Quiz attempts: tied either by user_id or by one of the person's tokens.
    quiz_q = select(QuizResult).where(QuizResult.user_id == user_id)
    quizzes = list(session.exec(quiz_q).all())
    if tokens:
        quizzes += session.exec(
            select(QuizResult).where(QuizResult.token.in_(tokens),
                                     QuizResult.user_id.is_(None))
        ).all()
    for q in quizzes:
        q.user_id = None
        q.token = ""
        session.add(q)

    placeholder = placeholder_email(user_id)
    for t in targets:
        t.email = placeholder
        t.name = ""
        t.consented = False
        t.token = secrets.token_urlsafe(16)  # old emailed links now 404
        session.add(t)

    links = session.exec(select(StaffGroupLink).where(StaffGroupLink.user_id == user_id)).all()
    for ln in links:
        session.delete(ln)

    # Audit history must not keep the address that was just erased.
    audits: list[AuditLog] = []
    if not already_erased and original_email:
        audits = session.exec(
            select(AuditLog).where(AuditLog.detail.contains(original_email))
        ).all()
        for a in audits:
            a.detail = a.detail.replace(original_email, REDACTED)
            session.add(a)

    user.email = placeholder
    user.name = ""
    user.department = ""
    user.consented = False
    user.erased_at = user.erased_at or utcnow()
    session.add(user)
    session.commit()

    return {
        "targets": len(targets),
        "events": len(events),
        "quiz_results": len(quizzes),
        "group_links": len(links),
        "audit_entries": len(audits),
    }
