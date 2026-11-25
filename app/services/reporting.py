"""Reporting a phish: the key *positive* awareness behaviour.

Two halves:

1. `record_report()` - decide whether a hit on a recipient's report link is a real
   person reporting, and record it exactly once. Email security gateways fetch
   every link in a message (including "Report this email"), so a bare GET must
   never count. The report link serves a confirmation page; the report is only
   recorded on the follow-up POST, which the page's JavaScript submits
   automatically (or the person presses the button if JS is off). Scanners do
   not run JS or submit forms, and the POST is still run through the same
   classifier as clicks (`app.detection.classify`) so a self-declared bot that
   does POST is rejected.

2. `campaign_report_metrics()` - report rate, time-to-first-report, median
   time-to-report, and "reported without clicking" vs "clicked then reported".

Pure-ish: takes a Session and plain values, no web framework.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

from sqlalchemy import func, update
from sqlmodel import Session, select

from app.detection import ClickSignals, ScannerNetwork, classify
from app.models import Campaign, Event, EventType, Target, Verdict, utcnow


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; everything here is UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _sent_time(target: Target, campaign: Campaign | None) -> datetime | None:
    return _aware(target.sent_at) or _aware(campaign.sent_at if campaign else None)


@dataclass
class ReportOutcome:
    counted: bool          # a new report was recorded by this call
    already: bool          # the recipient had already reported (idempotent no-op)
    verdict: str           # classifier verdict for this request
    reason: str


def record_report(session: Session, target: Target, campaign: Campaign | None, *,
                  user_agent: str, http_method: str, headers: dict | None,
                  js_confirmed: bool, ip: str, time_window_seconds: int = 15,
                  scanner_networks: tuple[ScannerNetwork, ...] = (),
                  ) -> ReportOutcome:
    """Record a confirmed report for `target`, at most once.

    Rejected (not counted) when the request looks automated by the same rules
    used for clicks: known scanner UA, prefetch header, HEAD, empty UA. The JS
    flag is deliberately NOT allowed to override those - a real browser never
    sends `curl/8` as its User-Agent.
    """
    sent = _sent_time(target, campaign)
    now = utcnow()
    secs = (now - sent).total_seconds() if sent else None
    if target.reported_at is not None:
        return ReportOutcome(False, True, Verdict.HUMAN.value, "already reported")

    base = classify(ClickSignals(user_agent=user_agent, http_method=http_method,
                                 seconds_since_send=secs, headers=headers,
                                 js_confirmed=False, ip=ip),
                    time_window_seconds=time_window_seconds,
                    scanner_networks=scanner_networks)
    if base.verdict == Verdict.SCANNER.value:
        return ReportOutcome(False, False, base.verdict, base.reason)

    # Conditional update = idempotent even under concurrent submits.
    res = session.exec(
        update(Target).where(Target.id == target.id, Target.reported_at.is_(None))
        .values(reported_at=now)
    )
    if res.rowcount != 1:
        session.rollback()
        return ReportOutcome(False, True, Verdict.HUMAN.value, "already reported")

    reason = ("report confirmed by page JavaScript (interactive browser)" if js_confirmed
              else "report confirmed by button press (no JavaScript)")
    session.add(Event(target_id=target.id, campaign_id=target.campaign_id,
                      type=EventType.REPORT, ip=ip, user_agent=user_agent,
                      http_method=http_method, verdict=Verdict.HUMAN, reason=reason,
                      seconds_since_send=secs))
    session.commit()
    session.refresh(target)
    return ReportOutcome(True, False, Verdict.HUMAN.value, reason)


def campaign_report_metrics(session: Session, campaign: Campaign) -> dict:
    """Reporting KPIs for one campaign.

    - report_rate: distinct reporters / recipients (percent)
    - time_to_first_report / median_time_to_report: seconds from the email being
      sent (per-recipient send time, else the campaign's) to the report
    - reported_without_click: reported and never (human-)clicked before reporting
    - clicked_then_reported: human click strictly before the report
    """
    targets = session.exec(select(Target).where(Target.campaign_id == campaign.id)).all()
    first_click = {
        tid: _aware(ts) for tid, ts in session.exec(
            select(Event.target_id, func.min(Event.created_at))
            .where(Event.campaign_id == campaign.id, Event.type == EventType.CLICK,
                   Event.verdict == Verdict.HUMAN)
            .group_by(Event.target_id)
        ).all()
    }
    reporters = [t for t in targets if t.reported_at is not None]
    durations: list[float] = []
    without_click = clicked_then = 0
    for t in reporters:
        rep = _aware(t.reported_at)
        sent = _sent_time(t, campaign)
        if sent is not None:
            durations.append(max(0.0, (rep - sent).total_seconds()))
        clicked = first_click.get(t.id)
        if clicked is not None and clicked <= rep:
            clicked_then += 1
        else:
            without_click += 1
    total = len(targets)
    return {
        "recipients": total,
        "reported": len(reporters),
        "report_rate": (len(reporters) / total * 100) if total else 0.0,
        "time_to_first_report": min(durations) if durations else None,
        "median_time_to_report": median(durations) if durations else None,
        "reported_without_click": without_click,
        "clicked_then_reported": clicked_then,
    }
