"""End-to-end: the whole phishing drill in dry-run mode, driven only over HTTP.

login -> users + group -> consent gate -> campaign -> send (dry-run) -> open
pixel -> browser click -> landing page -> JS beacon -> HUMAN; same link via curl
-> SCANNER; report; reports page + CSV reflect it; erasure removes the PII.

Tokens are recovered from the dry-run console output (what an operator would
copy), and the beacon URL is parsed out of the landing page HTML (what a real
browser would execute) rather than being reconstructed by the test.
"""
import csv
import io
import re

from fastapi.testclient import TestClient
from sqlmodel import select

from app.main import app
from app.models import (
    AuditLog,
    Campaign,
    CampaignStatus,
    Event,
    EventType,
    StaffGroup,
    Target,
    User,
    Verdict,
)
from tests.conftest import ADMIN

CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CURL = "curl/8.7.1"

ALICE = "alice.drill@example.com"
BOB = "bob.drill@example.com"


def _csv_rows(client) -> list[dict]:
    r = client.get("/reports/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(r.text)))


def test_full_drill_dry_run(capsys, session_factory):
    with TestClient(app) as web:
        # --- 1. Login ------------------------------------------------------
        r = web.get("/", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login")
        r = web.post("/login", data={"username": "admin", "password": "wrong", "next": "/"})
        assert r.status_code == 401
        r = web.post("/login", data={**ADMIN, "next": "/phishing"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/phishing"

        # --- 2. Users + group --------------------------------------------
        web.post("/users", data={"email": ALICE, "name": "Alice Drill",
                                 "department": "Finance", "consented": "on"})
        web.post("/users", data={"email": BOB, "name": "Bob NoConsent",
                                 "department": "Ops", "consented": "off"})
        web.post("/groups", data={"name": "Drill cohort", "description": "e2e"})
        with session_factory() as s:
            alice = s.exec(select(User).where(User.email == ALICE)).one()
            bob = s.exec(select(User).where(User.email == BOB)).one()
            alice_id, bob_id = alice.id, bob.id
            assert alice.consented is True and bob.consented is False
        page = web.get("/users").text
        assert ALICE in page and BOB in page and "Drill cohort" in page
        with session_factory() as s:
            gid = s.exec(select(StaffGroup.id).where(StaffGroup.name == "Drill cohort")).one()
        web.post("/users/assign", data={"group_id": gid, "user_ids": [alice_id, bob_id]})
        assert "Alice Drill" in web.get(f"/users?group={gid}").text

        # --- 3. Campaign, targeted by group --------------------------------
        r = web.post("/campaigns", data={"name": "Q4 payroll drill", "subject": "Payroll update",
                                         "from_name": "HR", "from_email": "hr@example.com"},
                     follow_redirects=False)
        cid = int(r.headers["location"].rsplit("/", 1)[-1])
        web.post(f"/campaigns/{cid}/targets_group", data={"group_id": gid})
        with session_factory() as s:
            targets = s.exec(select(Target).where(Target.campaign_id == cid)).all()
        assert {t.email for t in targets} == {ALICE, BOB}

        # --- 4. Send (dry-run) -- consent gate -------------------------------
        capsys.readouterr()
        r = web.post(f"/campaigns/{cid}/send", follow_redirects=False)
        assert r.status_code == 303
        out = capsys.readouterr().out
        assert "[DRY-RUN] Would send to: Alice Drill" in out
        assert BOB not in out, "non-consenting recipient must never be mailed"
        tokens = re.findall(r"Click URL:\s+\S+/t/click/(\S+)", out)
        assert len(tokens) == 1
        token = tokens[0]
        with session_factory() as s:
            camp = s.get(Campaign, cid)
            by_email = {t.email: t for t in
                        s.exec(select(Target).where(Target.campaign_id == cid)).all()}
        assert camp.status == CampaignStatus.SENT
        assert by_email[ALICE].token == token and by_email[ALICE].sent_at is not None
        assert by_email[BOB].sent_at is None
        assert "not marked as consenting" in by_email[BOB].send_error

        # Re-send is refused and mails nobody.
        r = web.post(f"/campaigns/{cid}/send", follow_redirects=False)
        assert "notice=already_sent" in r.headers["location"]
        assert "Would send" not in capsys.readouterr().out

    # The recipient side is a different, unauthenticated browser.
    with TestClient(app) as browser, TestClient(app) as scanner:
        # --- 5. Open pixel --------------------------------------------------
        r = browser.get(f"/t/open/{token}.png", headers={"User-Agent": CHROME})
        assert r.status_code == 200 and r.content.startswith(b"\x89PNG")

        # --- 6. Browser click -> landing -> JS beacon -> HUMAN --------------
        r = browser.get(f"/t/click/{token}", headers={"User-Agent": CHROME})
        assert r.status_code == 200
        assert "This was a phishing simulation" in r.text
        with session_factory() as s:
            click = s.exec(select(Event).where(Event.type == EventType.CLICK)).one()
        # Just sent -> inside the scan window, held as unknown until JS proves a browser.
        assert click.verdict == Verdict.UNKNOWN
        beacon = re.search(r'fetch\("(/t/confirm/[^"]+)"', r.text).group(1)
        assert beacon == f"/t/confirm/{token}"
        r = browser.post(beacon, headers={"User-Agent": CHROME})
        assert r.status_code == 204
        with session_factory() as s:
            click = s.get(Event, click.id)
            confirm = s.exec(select(Event).where(Event.type == EventType.CONFIRM)).one()
        assert click.verdict == Verdict.HUMAN
        assert "JavaScript" in click.reason
        assert confirm.verdict == Verdict.HUMAN

        # --- 7. Same link via curl -> SCANNER (and the human click survives) --
        r = scanner.get(f"/t/click/{token}", headers={"User-Agent": CURL})
        assert r.status_code == 200
        with session_factory() as s:
            clicks = s.exec(select(Event).where(Event.type == EventType.CLICK)
                            .order_by(Event.id)).all()
        assert [c.verdict for c in clicks] == [Verdict.HUMAN, Verdict.SCANNER]
        assert "'curl'" in clicks[1].reason and clicks[1].user_agent == CURL

        # --- 8. Report ------------------------------------------------------
        r = browser.get(f"/t/report/{token}", headers={"User-Agent": CHROME})
        assert r.status_code == 200

    with TestClient(app) as web:
        web.post("/login", data={**ADMIN, "next": "/"})

        # --- 9. Reports page, phishing list, dashboard, CSV -----------------
        rep = web.get("/reports").text
        assert ALICE in rep and "Alice Drill" in rep
        assert "scanner" in rep and "human" in rep
        with session_factory() as s:
            from app.services.risk import risk_scores
            row = next(r for r in risk_scores(s) if r["user"].email == ALICE)
        # open(+1) + one human click(+3) - report(2) = 2; the curl click is ignored.
        assert (row["opens"], row["human_clicks"], row["reports"], row["score"]) == (1, 1, 1, 2)
        assert web.get("/phishing").status_code == 200
        assert web.get(f"/campaigns/{cid}").status_code == 200
        assert web.get("/").status_code == 200

        rows = _csv_rows(web)
        mine = [r for r in rows if r["recipient_email"] == ALICE]
        assert [(r["type"], r["verdict"]) for r in mine] == [
            ("open", "unknown"), ("click", "human"), ("confirm", "human"),
            ("click", "scanner"), ("report", "human"),
        ]
        assert all(r["campaign"] == "Q4 payroll drill" for r in mine)
        assert mine[3]["user_agent"] == CURL and mine[1]["user_agent"] == CHROME
        assert all(r["ip"] for r in mine)

        # --- 10. Erasure ----------------------------------------------------
        r = web.post(f"/users/{alice_id}/erase", follow_redirects=False)
        assert r.headers["location"] == "/users?notice=erased"

        assert ALICE not in web.get("/reports").text
        assert ALICE not in web.get("/users").text
        assert ALICE not in web.get(f"/campaigns/{cid}").text
        rows = _csv_rows(web)
        blob = "\n".join(",".join(r.values()) for r in rows)
        assert ALICE not in blob and CHROME not in blob and CURL not in blob
        # Behavioural aggregates survive anonymisation.
        assert sum(1 for r in rows if r["type"] == "click" and r["verdict"] == "human") == 1
        assert sum(1 for r in rows if r["type"] == "click" and r["verdict"] == "scanner") == 1

        with session_factory() as s:
            u = s.get(User, alice_id)
            assert u.email == f"erased-{alice_id}@erased.invalid" and u.name == ""
            assert u.department == "" and u.consented is False and u.erased_at
            evs = s.exec(select(Event)).all()
            assert evs and all(e.ip == "" and e.user_agent == "" for e in evs)
            audits = s.exec(select(AuditLog)).all()
            assert not any(ALICE in a.detail for a in audits)
            assert any(a.action == "user.erase" for a in audits)
            # Bob was never touched by Alice's erasure.
            assert s.get(User, bob_id).email == BOB

    # Links already sitting in Alice's inbox are dead now.
    with TestClient(app) as browser:
        assert browser.get(f"/t/click/{token}", headers={"User-Agent": CHROME}).status_code == 404
        assert browser.post(f"/t/confirm/{token}").status_code == 404
        assert browser.get(f"/t/report/{token}").status_code == 404
        # The pixel always returns an image, but must not log anything.
        with session_factory() as s:
            n_before = len(s.exec(select(Event)).all())
        browser.get(f"/t/open/{token}.png")
        with session_factory() as s:
            assert len(s.exec(select(Event)).all()) == n_before
