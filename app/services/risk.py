"""Per-person risk scoring (the product's headline number).

Pure-ish: takes a Session, runs one grouped query, returns plain dicts. Weights
and band thresholds are named constants so the scoring rule is explicit.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Event, EventType, Target, User, Verdict

CLICK_WEIGHT = 3    # a human click = fell for it
OPEN_WEIGHT = 1
REPORT_WEIGHT = 2   # reporting is a good habit -> lowers risk
HIGH_BAND = 6
MEDIUM_BAND = 3


def risk_band(score: int) -> str:
    return "High" if score >= HIGH_BAND else "Medium" if score >= MEDIUM_BAND else "Low"


def risk_scores(session: Session) -> list[dict]:
    """Aggregate each user's behaviour across all campaigns into a risk score.

    human click = +3 (fell for it), open = +1, report = -2 (good habit).
    Scanner clicks are ignored - they are not the person. Higher = riskier.

    Event tallies come from a single grouped SQL query (O(rows), not
    O(users x events)).
    """
    users = session.exec(select(User)).all()
    target_user = dict(session.exec(select(Target.id, Target.user_id)).all())
    targets_per_user = Counter(target_user.values())  # one target per campaign

    opens: Counter[int] = Counter()
    human: Counter[int] = Counter()
    reports: Counter[int] = Counter()
    rows = session.exec(
        select(Event.target_id, Event.type, Event.verdict, func.count())
        .group_by(Event.target_id, Event.type, Event.verdict)
    ).all()
    for target_id, etype, verdict, n in rows:
        uid = target_user.get(target_id)
        if uid is None:
            continue
        if etype == EventType.OPEN:
            opens[uid] += n
        elif etype == EventType.CLICK and verdict == Verdict.HUMAN:
            human[uid] += n
        elif etype == EventType.REPORT:
            reports[uid] += n

    out = []
    for u in users:
        o, h, r = opens[u.id], human[u.id], reports[u.id]
        score = max(0, h * CLICK_WEIGHT + o * OPEN_WEIGHT - r * REPORT_WEIGHT)
        out.append({
            "user": u, "campaigns": targets_per_user.get(u.id, 0), "opens": o,
            "human_clicks": h, "reports": r, "score": score, "band": risk_band(score),
        })
    out.sort(key=lambda row: row["score"], reverse=True)
    return out
