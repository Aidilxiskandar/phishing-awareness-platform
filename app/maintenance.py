"""Data-retention maintenance.

Evidence rows (opens/clicks/reports) hold recipient IP + user-agent — PII under
GDPR/PDPA. This purges events older than the retention window so the data isn't
kept forever. Run from cron:

    python -m app.maintenance                    # purge expired events
    python -m app.maintenance erase EMAIL        # right-to-erasure for one person

Controlled by RETENTION_DAYS (0 = keep indefinitely).
"""
from __future__ import annotations

import logging
import sys
from datetime import timedelta

from sqlmodel import select

from app.config import settings
from app.database import get_session, init_db
from app.models import AuditLog, Event, User, utcnow
from app.services.erasure import erase_user

logger = logging.getLogger("phishguard.maintenance")


def purge_expired_events(days: int | None = None) -> int:
    """Delete events older than `days` (default: settings.retention_days).

    Returns the number of rows removed. A non-positive window is a no-op.
    """
    days = settings.retention_days if days is None else days
    if not days or days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=days)
    with get_session() as session:
        stale = session.exec(select(Event).where(Event.created_at < cutoff)).all()
        for event in stale:
            session.delete(event)
        session.commit()
    logger.info("purged %d events older than %d days", len(stale), days)
    return len(stale)


def erase_by_email(email: str) -> dict[str, int] | None:
    """Erase the (non-erased) user with this email. None if no such user."""
    with get_session() as session:
        user = session.exec(select(User).where(User.email == email.strip())).first()
        if user is None:
            return None
        counts = erase_user(session, user.id)
        session.add(AuditLog(actor="cli", action="user.erase",
                             detail=f"user #{user.id} erased via CLI"))
        session.commit()
        return counts


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO)
    init_db()
    if argv[:1] == ["erase"]:
        if len(argv) != 2:
            print("usage: python -m app.maintenance erase EMAIL", file=sys.stderr)
            return 2
        counts = erase_by_email(argv[1])
        if counts is None:
            print("No user with that email.", file=sys.stderr)
            return 1
        print("Erased. Rows anonymised: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        return 0
    removed = purge_expired_events()
    print(f"Purged {removed} event(s) older than {settings.retention_days} day(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
