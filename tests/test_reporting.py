"""First-class phish reporting: tracked link, idempotency, scanner filtering, metrics, risk."""
from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.mailer import render_email_html
from app.models import Campaign, Event, EventType, Target, User, Verdict
from app.services.reporting import campaign_report_metrics
from app.services.risk import risk_scores as _risk_scores

CHROME = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def _setup(session_factory, n=1, sent_ago=timedelta(hours=1)):
    """A sent campaign with `n` recipients; returns (campaign_id, [tokens])."""
    sent = datetime.now(UTC) - sent_ago
    with session_factory() as s:
        c = Campaign(name="Drill", sent_at=sent)
        s.add(c)
        s.commit()
        tokens = []
        for i in range(n):
            u = User(email=f"p{i}@example.com", consented=True)
            s.add(u)
            s.commit()
            t = Target(campaign_id=c.id, user_id=u.id, email=u.email, token=f"tok{i}",
                       consented=True, sent_at=sent)
            s.add(t)
            tokens.append(t.token)
        s.commit()
        return c.id, tokens


def _reports(session_factory):
    with session_factory() as s:
        return s.exec(select(Event).where(Event.type == EventType.REPORT)).all()


def _target(session_factory, token):
    with session_factory() as s:
        return s.exec(select(Target).where(Target.token == token)).one()


def _metrics(session_factory, cid):
    with session_factory() as s:
        return campaign_report_metrics(s, s.get(Campaign, cid))


def test_email_contains_per_recipient_report_link(session_factory):
    _, (tok,) = _setup(session_factory)
    t = _target(session_factory, tok)
    with session_factory() as s:
        c = s.get(Campaign, t.campaign_id)
    assert f"/t/report/{tok}" in render_email_html(c, t)
    # Admin preview must not carry a live report link.
    assert f"/t/report/{tok}" not in render_email_html(c, t, preview=True)


def test_get_serves_confirmation_page_and_records_nothing(anon, session_factory):
    _, (tok,) = _setup(session_factory)
    r = anon.get(f"/t/report/{tok}", headers={"user-agent": CHROME})
    assert r.status_code == 200
    assert 'action="/t/report/' in r.text and "submit()" in r.text
    assert _reports(session_factory) == []
    assert _target(session_factory, tok).reported_at is None


def test_unknown_token_404(anon):
    assert anon.get("/t/report/nope").status_code == 404
    assert anon.post("/t/report/nope", data={"js": "1"}).status_code == 404


def test_js_confirmed_report_recorded_with_praise(anon, session_factory):
    _, (tok,) = _setup(session_factory)
    r = anon.post(f"/t/report/{tok}", data={"js": "1"}, headers={"user-agent": CHROME})
    assert r.status_code == 200 and "Great catch" in r.text
    (ev,) = _reports(session_factory)
    assert ev.verdict == Verdict.HUMAN and "JavaScript" in ev.reason
    assert ev.seconds_since_send and ev.seconds_since_send > 3000
    assert _target(session_factory, tok).reported_at is not None


def test_button_press_without_js_is_recorded(anon, session_factory):
    _, (tok,) = _setup(session_factory)
    anon.post(f"/t/report/{tok}", data={"js": "0"}, headers={"user-agent": CHROME})
    (ev,) = _reports(session_factory)
    assert "button press" in ev.reason


def test_report_is_idempotent(anon, session_factory):
    _, (tok,) = _setup(session_factory)
    anon.post(f"/t/report/{tok}", data={"js": "1"}, headers={"user-agent": CHROME})
    first = _target(session_factory, tok).reported_at
    r = anon.post(f"/t/report/{tok}", data={"js": "1"}, headers={"user-agent": CHROME})
    assert "already reported" in r.text
    r = anon.get(f"/t/report/{tok}", headers={"user-agent": CHROME})
    assert "already reported" in r.text
    assert len(_reports(session_factory)) == 1
    assert _target(session_factory, tok).reported_at == first


def test_scanner_fetches_of_report_link_not_counted(anon, session_factory):
    cid, (tok,) = _setup(session_factory)
    # Gateway / preview bots fetch (GET/HEAD) every link in the email.
    for ua in ("Mozilla/5.0 (compatible; Barracuda Sentinel)", "curl/8.4.0", ""):
        anon.get(f"/t/report/{tok}", headers={"user-agent": ua})
    anon.head(f"/t/report/{tok}", headers={"user-agent": CHROME})
    anon.get(f"/t/report/{tok}", headers={"user-agent": CHROME, "sec-purpose": "prefetch"})
    # Even a POST claiming JS ran is rejected when the classifier says scanner.
    r = anon.post(f"/t/report/{tok}", data={"js": "1"},
                  headers={"user-agent": "python-requests/2.31"})
    assert r.status_code == 202
    anon.post(f"/t/report/{tok}", data={"js": "1"},
              headers={"user-agent": CHROME, "purpose": "prefetch"})
    assert _reports(session_factory) == []
    assert _target(session_factory, tok).reported_at is None
    assert _metrics(session_factory, cid)["reported"] == 0


def test_metrics_report_rate_timing_and_click_split(session_factory):
    cid, toks = _setup(session_factory, n=4, sent_ago=timedelta(hours=10))
    with session_factory() as s:
        c = s.get(Campaign, cid)
        sent = c.sent_at.replace(tzinfo=UTC) if c.sent_at.tzinfo is None else c.sent_at
        ts = {t.token: t for t in s.exec(select(Target)).all()}
        # tok0 reported after 10 min, no click; tok1 clicked at 1h then reported at 2h;
        # tok2 reported at 3h and clicked afterwards (still "without clicking" first).
        ts["tok0"].reported_at = sent + timedelta(minutes=10)
        ts["tok1"].reported_at = sent + timedelta(hours=2)
        ts["tok2"].reported_at = sent + timedelta(hours=3)
        s.add(Event(target_id=ts["tok1"].id, campaign_id=cid, type=EventType.CLICK,
                    verdict=Verdict.HUMAN, created_at=sent + timedelta(hours=1)))
        s.add(Event(target_id=ts["tok2"].id, campaign_id=cid, type=EventType.CLICK,
                    verdict=Verdict.HUMAN, created_at=sent + timedelta(hours=4)))
        # A scanner click must not make tok0 "clicked then reported".
        s.add(Event(target_id=ts["tok0"].id, campaign_id=cid, type=EventType.CLICK,
                    verdict=Verdict.SCANNER, created_at=sent + timedelta(seconds=1)))
        for t in ts.values():
            s.add(t)
        s.commit()
    m = _metrics(session_factory, cid)
    assert m["recipients"] == 4 and m["reported"] == 3
    assert m["report_rate"] == 75.0
    assert abs(m["time_to_first_report"] - 600) < 1
    assert abs(m["median_time_to_report"] - 7200) < 1
    assert m["reported_without_click"] == 2 and m["clicked_then_reported"] == 1


def test_metrics_empty_campaign(session_factory):
    with session_factory() as s:
        c = Campaign(name="Empty")
        s.add(c)
        s.commit()
        m = campaign_report_metrics(s, c)
    assert m["report_rate"] == 0.0 and m["time_to_first_report"] is None
    assert m["median_time_to_report"] is None


def test_campaign_page_shows_reporting_metrics(client, anon, session_factory):
    cid, toks = _setup(session_factory, n=2)
    anon.post(f"/t/report/{toks[0]}", data={"js": "1"}, headers={"user-agent": CHROME})
    body = client.get(f"/campaigns/{cid}").text
    assert "Report rate" in body and "50%" in body
    assert "Time to first report" in body and "Median time to report" in body
    assert "Reported without clicking" in body and "Clicked, then reported" in body


def _risk(session_factory, email):
    with session_factory() as s:
        return next(r for r in _risk_scores(s) if r["user"].email == email)


def test_reporting_lowers_risk_and_clean_report_lowers_more(anon, session_factory):
    _, toks = _setup(session_factory, n=3)
    with session_factory() as s:
        targets = {t.token: t for t in s.exec(select(Target)).all()}
        for tok in toks:  # everyone opened twice and... p0/p1 clicked
            for _ in range(2):
                s.add(Event(target_id=targets[tok].id, campaign_id=targets[tok].campaign_id,
                            type=EventType.OPEN, verdict=Verdict.UNKNOWN))
        for tok in ("tok0", "tok1"):
            s.add(Event(target_id=targets[tok].id, campaign_id=targets[tok].campaign_id,
                        type=EventType.CLICK, verdict=Verdict.HUMAN))
        s.commit()
    anon.post("/t/report/tok1", data={"js": "1"}, headers={"user-agent": CHROME})
    anon.post("/t/report/tok2", data={"js": "1"}, headers={"user-agent": CHROME})
    # Repeated submits don't keep lowering the score.
    anon.post("/t/report/tok2", data={"js": "1"}, headers={"user-agent": CHROME})
    no_report = _risk(session_factory, "p0@example.com")
    clicked_reported = _risk(session_factory, "p1@example.com")
    clean = _risk(session_factory, "p2@example.com")
    assert no_report["score"] == 5                 # 2 opens + 1 click
    assert clicked_reported["score"] == 3          # 5 - 2
    assert clean["score"] == 0                     # 2 - 2 - 1 -> floor 0
    assert clean["reports"] == 1 and clean["reported_without_click"] == 1
    assert clean["report_rate"] == 100.0


def test_scanner_report_events_do_not_lower_risk(session_factory):
    _, (tok,) = _setup(session_factory)
    with session_factory() as s:
        t = s.exec(select(Target)).one()
        s.add(Event(target_id=t.id, campaign_id=t.campaign_id, type=EventType.CLICK,
                    verdict=Verdict.HUMAN))
        s.add(Event(target_id=t.id, campaign_id=t.campaign_id, type=EventType.REPORT,
                    verdict=Verdict.SCANNER))
        s.commit()
    assert _risk(session_factory, "p0@example.com")["score"] == 3


def test_rejected_report_page_does_not_auto_submit_again(client, anon, session_factory):
    """Regression: a rejected (automated) report re-rendered the auto-submitting
    page, so a sandbox that runs JS POSTed in an endless loop."""
    from tests.test_tracking import _make_target
    _, token = _make_target(client, session_factory)
    first = anon.get(f"/t/report/{token}")
    assert "report-form\").submit()" in first.text            # normal page auto-submits
    r = anon.post(f"/t/report/{token}", data={"js": "1"},
                  headers={"User-Agent": "Mozilla/5.0 HeadlessChrome/131.0"})
    assert r.status_code == 202
    assert "report-form\").submit()" not in r.text            # rejection page doesn't
    assert "Yes, report it" in r.text                          # a person can still press it
