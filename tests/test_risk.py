"""Risk scoring (now SQL-aggregated): weights, band boundaries, aggregation."""
from app.services.risk import risk_scores as _risk_scores
from app.models import Campaign, Event, EventType, Target, User, Verdict

H = (EventType.CLICK, Verdict.HUMAN)
S = (EventType.CLICK, Verdict.SCANNER)
OPN = (EventType.OPEN, Verdict.UNKNOWN)
R = (EventType.REPORT, Verdict.HUMAN)


def _make_user_with_events(session_factory, specs, campaigns=1):
    """Create a user and `campaigns` targets, spreading `specs` across them."""
    with session_factory() as s:
        user = User(email="risk@example.com", consented=True)
        s.add(user)
        s.commit()
        targets = []
        for i in range(campaigns):
            c = Campaign(name=f"C{i}")
            s.add(c)
            s.commit()
            t = Target(campaign_id=c.id, user_id=user.id, email=user.email, token=f"rt{i}")
            s.add(t)
            s.commit()
            targets.append(t)
        for idx, (etype, verdict) in enumerate(specs):
            t = targets[idx % len(targets)]
            s.add(Event(target_id=t.id, campaign_id=t.campaign_id, type=etype, verdict=verdict))
        s.commit()
        return user.id


def _row(session_factory, uid):
    with session_factory() as s:
        return next(r for r in _risk_scores(s) if r["user"].id == uid)


def test_two_opens_is_low(session_factory):
    uid = _make_user_with_events(session_factory, [OPN, OPN])
    r = _row(session_factory, uid)
    assert r["score"] == 2 and r["band"] == "Low"


def test_one_human_click_is_medium(session_factory):
    uid = _make_user_with_events(session_factory, [H])
    r = _row(session_factory, uid)
    assert r["score"] == 3 and r["band"] == "Medium"


def test_two_human_clicks_is_high(session_factory):
    uid = _make_user_with_events(session_factory, [H, H])
    r = _row(session_factory, uid)
    assert r["score"] == 6 and r["band"] == "High"


def test_scanner_clicks_are_ignored(session_factory):
    uid = _make_user_with_events(session_factory, [S, S, S])
    r = _row(session_factory, uid)
    assert r["score"] == 0 and r["band"] == "Low"


def test_report_lowers_score(session_factory):
    uid = _make_user_with_events(session_factory, [H, R])  # 3 - 2 = 1
    r = _row(session_factory, uid)
    assert r["score"] == 1 and r["band"] == "Low"


def test_score_floors_at_zero(session_factory):
    uid = _make_user_with_events(session_factory, [R, R])  # -4 -> 0
    r = _row(session_factory, uid)
    assert r["score"] == 0


def test_aggregates_across_campaigns(session_factory):
    uid = _make_user_with_events(session_factory, [H, H], campaigns=2)
    r = _row(session_factory, uid)
    assert r["campaigns"] == 2
    assert r["score"] == 6 and r["band"] == "High"


def test_user_with_no_targets_scores_zero(session_factory):
    with session_factory() as s:
        u = User(email="idle@example.com", consented=True)
        s.add(u)
        s.commit()
        uid = u.id
    r = _row(session_factory, uid)
    assert r["score"] == 0 and r["campaigns"] == 0
