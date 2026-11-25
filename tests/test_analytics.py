"""Reporting aggregations (SQL-grouped) and the executive report route."""
from datetime import timedelta

from app.models import (
    Campaign,
    CampaignStatus,
    Event,
    EventType,
    QuizResult,
    StaffGroup,
    StaffGroupLink,
    Target,
    TrainingModule,
    User,
    Verdict,
    utcnow,
)
from app.services import analytics, charts

H = (EventType.CLICK, Verdict.HUMAN, "landing page JavaScript executed")
S = (EventType.CLICK, Verdict.SCANNER, "HTTP HEAD request")
U = (EventType.CLICK, Verdict.UNKNOWN, "no decisive signal")
OP = (EventType.OPEN, Verdict.UNKNOWN, "email open")
R = (EventType.REPORT, Verdict.HUMAN, "reported")


def _seed(s, name, people, sent_offset_days=0, status=CampaignStatus.SENT):
    """people: {email: [event specs]}. Users are reused across campaigns by email."""
    c = Campaign(name=name, status=status,
                 sent_at=utcnow() + timedelta(days=sent_offset_days))
    s.add(c)
    s.commit()
    for email, specs in people.items():
        from sqlmodel import select
        u = s.exec(select(User).where(User.email == email)).first()
        if u is None:
            u = User(email=email, name=email.split("@")[0].title(), department="Ops",
                     consented=True)
            s.add(u)
            s.commit()
        t = Target(campaign_id=c.id, user_id=u.id, email=email, name=u.name,
                   token=f"{name}-{email}", consented=True, sent_at=utcnow())
        s.add(t)
        s.commit()
        for etype, verdict, reason in specs:
            s.add(Event(target_id=t.id, campaign_id=c.id, type=etype, verdict=verdict,
                        reason=reason, seconds_since_send=2.0))
        s.commit()
    return c.id


def _users(s):
    from sqlmodel import select
    return {u.email: u.id for u in s.exec(select(User)).all()}


def test_campaign_trend_rates_are_per_person_and_ordered(session_factory):
    with session_factory() as s:
        _seed(s, "Later", {"a@x.com": [OP], "b@x.com": [R]}, sent_offset_days=5)
        _seed(s, "Early", {"a@x.com": [H, H, S, S, S], "b@x.com": [R, R],
                           "c@x.com": [], "d@x.com": [U]})
        _seed(s, "Draft", {"a@x.com": [H]}, status=CampaignStatus.DRAFT)
        trend = analytics.campaign_trend(s)
    assert [t["name"] for t in trend] == ["Early", "Later"]
    early = trend[0]
    assert early["targets"] == 4
    assert early["clicked"] == 1 and early["human_clicks"] == 2   # 2 clicks, 1 person
    assert early["click_rate"] == 25.0
    assert early["reported"] == 1 and early["report_rate"] == 25.0
    assert early["scanner_clicks"] == 3 and early["unknown_clicks"] == 1
    assert trend[1]["click_rate"] == 0.0 and trend[1]["report_rate"] == 50.0


def test_campaign_trend_skips_campaigns_without_recipients(session_factory):
    with session_factory() as s:
        _seed(s, "Empty", {})
        assert analytics.campaign_trend(s) == []


def test_group_breakdown(session_factory):
    with session_factory() as s:
        cid = _seed(s, "C1", {"a@x.com": [H, S], "b@x.com": [R], "c@x.com": []})
        _seed(s, "C2", {"a@x.com": [], "b@x.com": [H]}, sent_offset_days=1)
        ids = _users(s)
        g1, g2, g3 = StaffGroup(name="Finance"), StaffGroup(name="IT"), StaffGroup(name="Idle")
        s.add_all([g1, g2, g3])
        s.commit()
        s.add_all([StaffGroupLink(user_id=ids["a@x.com"], group_id=g1.id),
                   StaffGroupLink(user_id=ids["b@x.com"], group_id=g1.id),
                   StaffGroupLink(user_id=ids["c@x.com"], group_id=g2.id)])
        s.commit()
        rows = {g["name"]: g for g in analytics.group_breakdown(s)}
        scoped = {g["name"]: g for g in analytics.group_breakdown(s, cid)}
    fin = rows["Finance"]
    assert fin["members"] == 2 and fin["targets"] == 4
    assert fin["clicked"] == 2 and fin["click_rate"] == 50.0
    assert fin["reported"] == 1 and fin["scanner_clicks"] == 1
    assert rows["IT"]["targets"] == 1 and rows["IT"]["click_rate"] == 0.0
    assert rows["Idle"]["members"] == 0 and rows["Idle"]["targets"] == 0
    assert scoped["Finance"]["targets"] == 2 and scoped["Finance"]["clicked"] == 1
    # Worst click rate first.
    assert analytics.group_breakdown.__doc__ and list(rows)[0] == "Finance"


def test_click_evidence_and_top_risk(session_factory):
    with session_factory() as s:
        cid = _seed(s, "C", {"a@x.com": [H, H, OP], "b@x.com": [S, S], "c@x.com": [H, R],
                             "d@x.com": [R]})
        ev = analytics.click_evidence(s, cid)
        top = analytics.campaign_top_risk(s, cid)
    by_verdict = {e["verdict"]: e for e in ev}
    assert by_verdict["human"]["count"] == 3 and by_verdict["scanner"]["count"] == 2
    assert by_verdict["scanner"]["reason"] == "HTTP HEAD request"
    assert by_verdict["human"]["fastest"] == 2.0
    # a: 3+3+1=7 High; c: 3-2=1 Low; b (scanner only) and d (report only) excluded.
    assert [r["email"] for r in top] == ["a@x.com", "c@x.com"]
    assert top[0]["score"] == 7 and top[0]["band"] == "High"
    assert top[0]["department"] == "Ops"


def test_campaign_report_kpis_and_previous(session_factory):
    with session_factory() as s:
        _seed(s, "Prev", {"a@x.com": [H], "b@x.com": [H]})
        cid = _seed(s, "Now", {"a@x.com": [H, S], "b@x.com": [R], "c@x.com": [U]},
                    sent_offset_days=1)
        mod = TrainingModule(slug="zz-test", title="T")
        s.add(mod)
        s.commit()
        s.add(QuizResult(module_id=mod.id, token="Now-a@x.com", score=3, total=3))
        s.commit()
        rep = analytics.campaign_report(s, cid)
        assert analytics.campaign_report(s, 9999) is None
    k = rep["kpis"]
    assert k["targets"] == 3 and k["delivered"] == 3
    assert k["clicked"] == 1 and k["trained_clickers"] == 1
    assert k["raw_clicks"] == 3 and round(k["scanner_share"]) == 33
    assert rep["prev"]["name"] == "Prev"
    titles = [r["title"] for r in rep["recommendations"]]
    assert "Improving on the previous drill" in titles
    assert "Scanner traffic was filtered" in titles
    assert "Review unclassified clicks" in titles


def _k(**over):
    base = {"targets": 10, "clicked": 0, "trained_clickers": 0, "click_rate": 0.0,
            "report_rate": 50.0, "scanner_clicks": 0, "unknown_clicks": 0}
    return {**base, **over}


def test_recommendations_rules():
    assert analytics.recommendations(_k(targets=0), [])[0]["title"] == "No recipients yet"
    ok = analytics.recommendations(_k(), [])
    assert [r["level"] for r in ok] == ["ok"]
    high = analytics.recommendations(
        _k(click_rate=40.0, clicked=4, trained_clickers=1, report_rate=10.0),
        [{"name": "Sales", "targets": 5, "click_rate": 60.0}],
        prev={"name": "Old", "click_rate": 20.0})
    titles = [r["title"] for r in high]
    assert titles[0] == "Run organisation-wide refresher training"
    assert "Follow up on untrained clickers" in titles
    assert "Promote the report button" in titles
    assert any("Sales" in t for t in titles)
    assert "Worse than the previous drill" in titles
    mid = analytics.recommendations(_k(click_rate=10.0), [])
    assert mid[0]["level"] == "watch"


def test_chart_geometry():
    series = [{"name": "A", "click_rate": 20.0, "report_rate": 5.0, "scanner_clicks": 4},
              {"name": "B", "click_rate": 0.0, "report_rate": 45.0, "scanner_clicks": 0}]
    mt = charts.multi_trend(series, ["click_rate", "report_rate"])
    assert mt["top"] == 50
    assert len(mt["lines"]["click_rate"]["pts"]) == 2
    assert mt["lines"]["click_rate"]["pts"][1]["y"] == mt["base"]   # 0% sits on the axis
    b = charts.bars(series, "scanner_clicks")
    assert b["bars"][0]["h"] > 0 and b["bars"][1]["h"] == 0
    assert charts.multi_trend([], ["click_rate"])["lines"]["click_rate"]["pts"] == []
    assert charts.bars([], "scanner_clicks")["bars"] == []


def test_report_route_renders(client, session_factory):
    with session_factory() as s:
        cid = _seed(s, "Q4 drill", {"alice@x.com": [H], "bob@x.com": [S, R]})
        g = StaffGroup(name="Finance")
        s.add(g)
        s.commit()
        s.add(StaffGroupLink(user_id=_users(s)["alice@x.com"], group_id=g.id))
        s.commit()
    r = client.get(f"/reports/campaigns/{cid}")
    assert r.status_code == 200
    body = r.text
    assert "Q4 drill" in body and "executive report" in body
    assert "HTTP HEAD request" in body          # scanner evidence reason shown
    assert "alice@x.com" in body                # top-risk person
    assert "Recommendations" in body and "@media print" in body
    reports = client.get("/reports")
    assert reports.status_code == 200
    assert "Trend over campaigns" in reports.text and "Finance" in reports.text
    assert f"/reports/campaigns/{cid}" in reports.text


def test_report_route_404_and_auth(client, anon):
    assert client.get("/reports/campaigns/424242").status_code == 404
    r = anon.get("/reports/campaigns/1", follow_redirects=False)
    assert r.status_code == 303
