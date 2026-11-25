"""Reporting aggregations: campaign trend, group breakdown, executive report.

Every function takes a Session and returns plain dicts. Counting happens in SQL
(GROUP BY / COUNT(DISTINCT) / SUM(CASE ...)), so cost scales with the number of
rows, never users x events (see risk.py for the same pattern).

Rates are per *person*, not per event: a recipient who clicks three times is one
clicker. Scanner clicks are reported as raw fetch counts, because each one is a
fetch that would have inflated a naive click number.
"""
from __future__ import annotations

from sqlalchemy import and_, case, func
from sqlmodel import Session, select

from app.models import (
    Campaign,
    CampaignStatus,
    Event,
    EventType,
    QuizResult,
    StaffGroup,
    StaffGroupLink,
    Target,
    User,
    Verdict,
)
from app.services import charts
from app.services.risk import CLICK_WEIGHT, OPEN_WEIGHT, REPORT_WEIGHT, risk_band

# Thresholds used by the recommendations. Named so the rules are explicit.
HIGH_CLICK_RATE = 20.0      # % of recipients clicking: needs organisation-wide action
TARGET_CLICK_RATE = 5.0     # % a mature programme aims to stay under
LOW_REPORT_RATE = 30.0      # % reporting below this: the report habit isn't there yet
GROUP_HOTSPOT_GAP = 10.0    # pts above the campaign rate before a group is called out
TOP_RISK_LIMIT = 10

_IS_HUMAN_CLICK = and_(Event.type == EventType.CLICK, Event.verdict == Verdict.HUMAN)
_IS_SCANNER_CLICK = and_(Event.type == EventType.CLICK, Event.verdict == Verdict.SCANNER)
_IS_UNKNOWN_CLICK = and_(Event.type == EventType.CLICK, Event.verdict == Verdict.UNKNOWN)
_IS_OPEN = Event.type == EventType.OPEN
_IS_REPORT = Event.type == EventType.REPORT


def _pct(part: int, whole: int) -> float:
    return (part / whole * 100) if whole else 0.0


def _distinct_targets(cond):
    """COUNT(DISTINCT target) where `cond` holds (NULLs from CASE are skipped)."""
    return func.count(func.distinct(case((cond, Event.target_id))))


def _sum_if(cond):
    return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)


def _per_campaign_counts(session: Session, campaign_ids: list[int] | None = None) -> dict:
    """One grouped query: per-campaign distinct openers/clickers/reporters and
    raw scanner/unknown click counts."""
    q = select(
        Event.campaign_id,
        _distinct_targets(_IS_OPEN),
        _distinct_targets(_IS_HUMAN_CLICK),
        _distinct_targets(_IS_REPORT),
        _sum_if(_IS_HUMAN_CLICK),
        _sum_if(_IS_SCANNER_CLICK),
        _sum_if(_IS_UNKNOWN_CLICK),
    ).group_by(Event.campaign_id)
    if campaign_ids is not None:
        q = q.where(Event.campaign_id.in_(campaign_ids))
    out = {}
    for cid, opened, clicked, reported, human, scanner, unknown in session.exec(q).all():
        out[cid] = {"opened": opened, "clicked": clicked, "reported": reported,
                    "human_clicks": int(human), "scanner_clicks": int(scanner),
                    "unknown_clicks": int(unknown)}
    return out


def _empty_counts() -> dict:
    return {"opened": 0, "clicked": 0, "reported": 0,
            "human_clicks": 0, "scanner_clicks": 0, "unknown_clicks": 0}


def campaign_trend(session: Session) -> list[dict]:
    """Per sent campaign, oldest first: recipients, human click rate, report rate
    and scanner clicks filtered. Two grouped queries regardless of size."""
    campaigns = session.exec(
        select(Campaign).where(Campaign.status == CampaignStatus.SENT)
    ).all()
    campaigns = sorted(campaigns, key=lambda c: (c.sent_at or c.created_at, c.id))
    targets = dict(session.exec(
        select(Target.campaign_id, func.count()).group_by(Target.campaign_id)
    ).all())
    counts = _per_campaign_counts(session)
    out = []
    for c in campaigns:
        n = targets.get(c.id, 0)
        if not n:
            continue
        k = counts.get(c.id, _empty_counts())
        out.append({
            "id": c.id, "name": c.name, "sent_at": c.sent_at or c.created_at,
            "targets": n, **k,
            "click_rate": _pct(k["clicked"], n),
            "report_rate": _pct(k["reported"], n),
            "open_rate": _pct(k["opened"], n),
            # Back-compat with charts.trend(): "rate" is the headline line.
            "rate": _pct(k["clicked"], n),
        })
    return out


def group_breakdown(session: Session, campaign_id: int | None = None) -> list[dict]:
    """Per staff group: members, recipients sent to, distinct human clickers and
    reporters, scanner clicks. Optionally scoped to one campaign.

    A user in two groups counts in both (groups overlap by design). Sorted by
    human click rate, worst first.
    """
    members = dict(session.exec(
        select(StaffGroupLink.group_id, func.count())
        .join(User, User.id == StaffGroupLink.user_id)
        .where(User.erased_at.is_(None))
        .group_by(StaffGroupLink.group_id)
    ).all())

    target_join = Target.user_id == StaffGroupLink.user_id
    if campaign_id is not None:
        target_join = and_(target_join, Target.campaign_id == campaign_id)
    q = (
        select(
            StaffGroup.id, StaffGroup.name,
            func.count(func.distinct(Target.id)),
            _distinct_targets(_IS_HUMAN_CLICK),
            _distinct_targets(_IS_REPORT),
            _sum_if(_IS_SCANNER_CLICK),
        )
        .select_from(StaffGroup)
        .join(StaffGroupLink, StaffGroupLink.group_id == StaffGroup.id, isouter=True)
        .join(Target, target_join, isouter=True)
        .join(Event, Event.target_id == Target.id, isouter=True)
        .group_by(StaffGroup.id, StaffGroup.name)
    )
    out = []
    for gid, name, sent, clicked, reported, scanner in session.exec(q).all():
        out.append({
            "id": gid, "name": name, "members": members.get(gid, 0),
            "targets": sent, "clicked": clicked, "reported": reported,
            "scanner_clicks": int(scanner),
            "click_rate": _pct(clicked, sent), "report_rate": _pct(reported, sent),
        })
    out.sort(key=lambda g: (-g["click_rate"], g["name"].lower()))
    return out


def click_evidence(session: Session, campaign_id: int) -> list[dict]:
    """Click events grouped by (verdict, reason): the "why" behind every number."""
    rows = session.exec(
        select(Event.verdict, Event.reason, func.count(),
               func.min(Event.seconds_since_send))
        .where(Event.campaign_id == campaign_id, Event.type == EventType.CLICK)
        .group_by(Event.verdict, Event.reason)
        .order_by(Event.verdict, func.count().desc())
    ).all()
    return [{"verdict": v.value if hasattr(v, "value") else str(v), "reason": r or "—",
             "count": n, "fastest": fastest} for v, r, n, fastest in rows]


def campaign_top_risk(session: Session, campaign_id: int,
                      limit: int = TOP_RISK_LIMIT) -> list[dict]:
    """Highest-risk recipients in one campaign, scored with the same weights as
    the cross-campaign risk score. Scored in SQL; only the top rows come back."""
    opens = _sum_if(_IS_OPEN)
    human = _sum_if(_IS_HUMAN_CLICK)
    reports = _sum_if(_IS_REPORT)
    raw = human * CLICK_WEIGHT + opens * OPEN_WEIGHT - reports * REPORT_WEIGHT
    rows = session.exec(
        select(Target.id, Target.name, Target.email, User.department,
               opens, human, reports, raw.label("raw"))
        .join(Event, Event.target_id == Target.id)
        .join(User, User.id == Target.user_id, isouter=True)
        .where(Target.campaign_id == campaign_id)
        .group_by(Target.id, Target.name, Target.email, User.department)
        .having(raw > 0)
        .order_by(raw.desc(), Target.email)
        .limit(limit)
    ).all()
    out = []
    for _tid, name, email, dept, o, h, r, score in rows:
        score = max(0, int(score))
        out.append({"name": name, "email": email, "department": dept or "",
                    "opens": int(o), "human_clicks": int(h), "reports": int(r),
                    "score": score, "band": risk_band(score)})
    return out


def _trained_clickers(session: Session, campaign_id: int) -> int:
    """Distinct human clickers in this campaign who then completed a quiz."""
    clicked = (
        select(Event.target_id)
        .where(Event.campaign_id == campaign_id, _IS_HUMAN_CLICK)
        .distinct()
        .subquery()
    )
    return session.exec(
        select(func.count(func.distinct(Target.id)))
        .join(clicked, clicked.c.target_id == Target.id)
        .join(QuizResult, QuizResult.token == Target.token)
    ).one()


def recommendations(k: dict, groups: list[dict], prev: dict | None = None) -> list[dict]:
    """Plain-language next steps derived from the KPIs. Pure; easy to unit test.

    Each item: {"level": "act" | "watch" | "ok", "title": str, "detail": str}.
    """
    recs: list[dict] = []
    if not k["targets"]:
        return [{"level": "watch", "title": "No recipients yet",
                 "detail": "Add recipients and send the drill to produce a report."}]

    rate, report_rate = k["click_rate"], k["report_rate"]
    if rate >= HIGH_CLICK_RATE:
        recs.append({"level": "act", "title": "Run organisation-wide refresher training",
                     "detail": f"{rate:.0f}% of recipients clicked. Above {HIGH_CLICK_RATE:.0f}% "
                               "the problem is general, not a few individuals."})
    elif rate > TARGET_CLICK_RATE:
        recs.append({"level": "watch", "title": "Target training at the people who clicked",
                     "detail": f"{rate:.0f}% clicked, above the {TARGET_CLICK_RATE:.0f}% "
                               "a mature programme aims for."})
    else:
        recs.append({"level": "ok", "title": "Click rate is within target",
                     "detail": f"{rate:.0f}% clicked (target under {TARGET_CLICK_RATE:.0f}%). "
                               "Raise difficulty on the next drill."})

    if k["clicked"] and k["trained_clickers"] < k["clicked"]:
        missing = k["clicked"] - k["trained_clickers"]
        recs.append({"level": "act", "title": "Follow up on untrained clickers",
                     "detail": f"{missing} of {k['clicked']} people who clicked have not "
                               "completed a training module yet."})

    if report_rate < LOW_REPORT_RATE:
        recs.append({"level": "watch", "title": "Promote the report button",
                     "detail": f"Only {report_rate:.0f}% reported the email. Reporting is the "
                               "behaviour that stops a real attack early."})

    hot = [g for g in groups if g["targets"] and g["click_rate"] >= rate + GROUP_HOTSPOT_GAP]
    if hot:
        g = hot[0]
        recs.append({"level": "act", "title": f"Focus on group “{g['name']}”",
                     "detail": f"{g['click_rate']:.0f}% of this group clicked, "
                               f"{g['click_rate'] - rate:.0f} pts above the campaign."})

    if k["scanner_clicks"]:
        recs.append({"level": "ok", "title": "Scanner traffic was filtered",
                     "detail": f"{k['scanner_clicks']} automated link fetches were excluded "
                               "from the human numbers. Allowlist the simulation domain in the "
                               "mail gateway to cut the noise further."})
    if k["unknown_clicks"]:
        recs.append({"level": "watch", "title": "Review unclassified clicks",
                     "detail": f"{k['unknown_clicks']} clicks had no decisive signal. "
                               "Check the evidence before counting them either way."})

    if prev is not None:
        diff = rate - prev["click_rate"]
        if diff <= -1:
            recs.append({"level": "ok", "title": "Improving on the previous drill",
                         "detail": f"Click rate down {-diff:.0f} pts from "
                                   f"“{prev['name']}”."})
        elif diff >= 1:
            recs.append({"level": "act", "title": "Worse than the previous drill",
                         "detail": f"Click rate up {diff:.0f} pts from "
                                   f"“{prev['name']}”."})
    return recs


def reports_overview(session: Session) -> dict:
    """Template context for the Reports tab's trend + group sections."""
    trend = campaign_trend(session)
    return {
        "trend": trend,
        "trend_chart": charts.multi_trend(trend, ["click_rate", "report_rate"]),
        "scanner_chart": charts.bars(trend, "scanner_clicks"),
        "groups": group_breakdown(session),
    }


def campaign_report(session: Session, campaign_id: int) -> dict | None:
    """Everything the executive report page needs for one campaign."""
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        return None

    targets, delivered = session.exec(
        select(func.count(), func.count(Target.sent_at))
        .where(Target.campaign_id == campaign_id)
    ).one()
    k = {"targets": targets, "delivered": delivered,
         **_per_campaign_counts(session, [campaign_id]).get(campaign_id, _empty_counts())}
    k["click_rate"] = _pct(k["clicked"], targets)
    k["report_rate"] = _pct(k["reported"], targets)
    k["open_rate"] = _pct(k["opened"], targets)
    k["trained_clickers"] = _trained_clickers(session, campaign_id)
    raw_clicks = k["human_clicks"] + k["scanner_clicks"] + k["unknown_clicks"]
    k["raw_clicks"] = raw_clicks
    k["scanner_share"] = _pct(k["scanner_clicks"], raw_clicks)

    trend = campaign_trend(session)
    idx = next((i for i, row in enumerate(trend) if row["id"] == campaign_id), None)
    prev = trend[idx - 1] if idx else None

    groups = [g for g in group_breakdown(session, campaign_id) if g["targets"]]
    return {
        "campaign": campaign,
        "kpis": k,
        "prev": prev,
        "evidence": click_evidence(session, campaign_id),
        "top_risk": campaign_top_risk(session, campaign_id),
        "groups": groups,
        "recommendations": recommendations(k, groups, prev),
    }
