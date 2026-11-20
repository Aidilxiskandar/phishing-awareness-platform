"""Data-retention purge."""
from datetime import timedelta

from sqlmodel import select

from app.maintenance import purge_expired_events
from app.models import Campaign, Event, EventType, Target, User, utcnow


def _seed_event(session_factory, age_days: float):
    with session_factory() as s:
        user = User(email=f"u{age_days}@example.com", consented=True)
        s.add(user)
        s.commit()
        campaign = Campaign(name="C")
        s.add(campaign)
        s.commit()
        target = Target(campaign_id=campaign.id, user_id=user.id,
                        email=user.email, token=f"tok{age_days}")
        s.add(target)
        s.commit()
        event = Event(target_id=target.id, campaign_id=campaign.id, type=EventType.OPEN,
                      created_at=utcnow() - timedelta(days=age_days))
        s.add(event)
        s.commit()


def _event_count(session_factory):
    with session_factory() as s:
        return len(s.exec(select(Event)).all())


def test_disabled_retention_is_noop(session_factory):
    _seed_event(session_factory, age_days=400)
    assert purge_expired_events(days=0) == 0
    assert _event_count(session_factory) == 1


def test_purge_removes_only_old_events(session_factory):
    _seed_event(session_factory, age_days=400)   # should be purged
    _seed_event(session_factory, age_days=5)      # should be kept
    removed = purge_expired_events(days=90)
    assert removed == 1
    assert _event_count(session_factory) == 1
