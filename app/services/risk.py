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
REPORT_WEIGHT = 2   # reporting is a good habit -> lowers risk (once per campaign)
REPORT_NO_CLICK_BONUS = 1  # extra credit: reported it without ever clicking
HIGH_BAND = 6
MEDIUM_BAND = 3


def risk_band(score: int) -> str:
    return "High" if score >= HIGH_BAND else "Medium" if score >= MEDIUM_BAND else "Low"


def risk_scores(session: Session) -> list[dict]:
    """Aggregate each user's behaviour across all campaigns into a risk score.

    human click = +3 (fell for it), open = +1, report = -2 per campaign reported
    (good habit), and a further -1 when that report came without a human click.
    Scanner clicks are ignored - they are not the person - and only HUMAN-verdict
    reports count (scanner fetches of the report link never create one).
    Higher = riskier.

    Event tallies come from a single grouped SQL query (O(rows), not
    O(users x events)).
    """
    users = session.exec(select(User).where(User.erased_at.is_(None))).all()
    target_user = dict(session.exec(select(Target.id, Target.user_id)).all())
    targets_per_user = Counter(target_user.values())  # one target per campaign

    opens: Counter[int] = Counter()
    human: Counter[int] = Counter()
    clicked_targets: set[int] = set()
    reported_targets: set[int] = set()
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
            clicked_targets.add(target_id)
        elif etype == EventType.REPORT and verdict == Verdict.HUMAN:
            # One report per campaign per person (the report endpoint is
            # idempotent; this also guards legacy duplicate rows).
            reported_targets.add(target_id)

    reports: Counter[int] = Counter(target_user[t] for t in reported_targets)
    clean_reports: Counter[int] = Counter(
        target_user[t] for t in reported_targets - clicked_targets)

    out = []
    for u in users:
        o, h, r, rc = opens[u.id], human[u.id], reports[u.id], clean_reports[u.id]
        n_campaigns = targets_per_user.get(u.id, 0)
        score = max(0, h * CLICK_WEIGHT + o * OPEN_WEIGHT
                    - r * REPORT_WEIGHT - rc * REPORT_NO_CLICK_BONUS)
        out.append({
            "user": u, "campaigns": n_campaigns, "opens": o,
            "human_clicks": h, "reports": r, "reported_without_click": rc,
            "report_rate": (r / n_campaigns * 100) if n_campaigns else 0.0,
            "score": score, "band": risk_band(score),
        })
    out.sort(key=lambda row: row["score"], reverse=True)
    return out
