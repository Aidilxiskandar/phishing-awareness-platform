"""Data-retention maintenance.

Evidence rows (opens/clicks/reports) hold recipient IP + user-agent — PII under
GDPR/PDPA. This purges events older than the retention window so the data isn't
kept forever. Run from cron:

    python -m app.maintenance

Controlled by RETENTION_DAYS (0 = keep indefinitely).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlmodel import select

from app.config import settings
from app.database import get_session, init_db
from app.models import Event, utcnow

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    removed = purge_expired_events()
    print(f"Purged {removed} event(s) older than {settings.retention_days} day(s).")
