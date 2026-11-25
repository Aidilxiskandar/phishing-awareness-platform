"""Simulate a full phishing drill against ~300 fake staff, end to end over HTTP.

Drives a *running* PhishGuard server the way the real world would:

  1. Admin logs in, generates N staff (example.com, ~90% consenting), creates a
     campaign, targets everyone and sends it (dry-run: nothing is emailed).
  2. Right after delivery, a mail security gateway (SafeLinks-style) prefetches a
     share of the links with HEAD/GET + scanner User-Agents from cloud IPs.
     -> these must land as SCANNER, never human.
  3. After the scanner window, staff behave like staff: some open the email
     (pixel), some click on desktop/mobile browsers and the landing page's
     JavaScript confirms them, a few click with JS blocked, some report the
     email, and some clickers take the follow-up training quiz.

Click/report propensity varies by department so the Reports tab has a story.

Usage (start a throwaway demo server first; see --help or the README note):
    DATABASE_URL=sqlite:///demo.db TRUSTED_PROXIES=127.0.0.1 \
        .venv/bin/uvicorn app.main:app --port 8765
    .venv/bin/python scripts/simulate_drill.py --base http://127.0.0.1:8765 --db demo.db

Only ever point this at a local demo server and database.
"""
from __future__ import annotations

import argparse
import random
import re
import sqlite3
import sys
import time
from collections import Counter

import httpx


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not m:
        sys.exit("No CSRF token on the page - is this a PhishGuard server?")
    return m.group(1)


# --- realistic client fingerprints -------------------------------------------

SCANNER_UAS = [
    "Mozilla/5.0 (compatible; Microsoft Office Protocol Discovery)",
    "Microsoft Office/16.0 (Windows NT 10.0; Microsoft Outlook 16.0.17126; Pro)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "HeadlessChrome/124.0.6367.207 Safari/537.36",
    "python-requests/2.31.0",
    "Go-http-client/1.1",
    "curl/8.4.0",
    "",  # empty UA, a classic probe
]
# Cloud ranges typical of gateway scanners (Microsoft / Proofpoint-like / AWS).
SCANNER_NETS = ["40.94.{}.{}", "52.101.{}.{}", "104.47.{}.{}", "148.163.{}.{}", "54.240.{}.{}"]

DESKTOP_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]
MOBILE_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; 2201117TG) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Mobile Safari/537.36",
]
MAIL_CLIENT_UAS = [  # who loads the open-pixel
    "Microsoft Office/16.0 (Windows NT 10.0; Microsoft Outlook 16.0.17126; Pro)",
    "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
]

# Relative click propensity by department (1.0 = average).
DEPT_CLICK = {
    "Finance": 1.6, "Procurement": 1.5, "Customer Service": 1.4, "Sales": 1.3,
    "Administration": 1.3, "Human Resources": 1.2, "Marketing": 1.1, "Operations": 1.0,
    "Corporate Affairs": 0.9, "Legal": 0.8, "Internal Audit": 0.6, "Compliance": 0.6,
    "Risk Management": 0.5, "Information Technology": 0.4,
}
DEPT_REPORT = {"Information Technology": 2.5, "Risk Management": 2.0, "Compliance": 1.8,
               "Internal Audit": 1.8, "Legal": 1.3}

BASE = {"open": 0.62, "click": 0.17, "report": 0.11, "scan": 0.35,
        "nojs": 0.12, "mobile": 0.35, "quiz": 0.55}


def office_ip() -> str:
    # Corporate NAT / home broadband addresses (TEST-NET and private-looking ranges).
    return random.choice([f"203.0.113.{random.randint(2, 254)}",
                          f"198.51.100.{random.randint(2, 254)}",
                          f"175.139.{random.randint(0, 255)}.{random.randint(1, 254)}"])


def scanner_ip() -> str:
    return random.choice(SCANNER_NETS).format(random.randint(0, 255), random.randint(1, 254))


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--db", default="demo.db", help="SQLite file the demo server uses")
    ap.add_argument("--staff", type=int, default=300)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="phishguard-dev")
    ap.add_argument("--window", type=int, default=15, help="server scanner window (s)")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    if not args.base.startswith(("http://127.0.0.1", "http://localhost")):
        sys.exit("Refusing: only run the simulator against a local demo server.")

    admin = httpx.Client(base_url=args.base, follow_redirects=True, timeout=30)
    origin = {"Origin": args.base}

    step("Admin login")
    try:
        page = admin.get("/login")
    except httpx.ConnectError:
        sys.exit(f"Can't reach {args.base}. Start the demo server first (see --help).")
    origin["X-CSRF-Token"] = _csrf(page.text)
    r = admin.post("/login", data={"username": args.user, "password": args.password,
                                   "next": "/"}, headers=origin)
    if r.status_code != 200 or "/login" in str(r.url):
        sys.exit(f"Login failed ({r.status_code}). Is the demo server running at {args.base}?")
    origin["X-CSRF-Token"] = _csrf(r.text)  # the token rotates on login

    step(f"Generating {args.staff} staff")
    admin.post("/users/seed", data={"count": str(args.staff)}, headers=origin).raise_for_status()

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    users = db.execute("SELECT id, department, consented FROM user WHERE erased_at IS NULL").fetchall()
    print(f"    directory now has {len(users)} people "
          f"({sum(u['consented'] for u in users)} consenting)")

    step("Creating campaign")
    r = admin.post("/campaigns", headers=origin, data={
        "name": f"Q4 Payroll Update Drill ({time.strftime('%d %b %H:%M')})",
        "subject": "Action required: confirm your December payroll details",
        "from_name": "Acme HR Payroll",
        "from_email": "payroll@acme-hr.example",
    })
    r.raise_for_status()
    cid = int(str(r.url).rstrip("/").split("/")[-1])
    print(f"    campaign #{cid}")

    step("Targeting everyone in the directory")
    admin.post(f"/campaigns/{cid}/targets", headers=origin,
               data={"user_ids": [str(u["id"]) for u in users]}).raise_for_status()

    step("Sending (dry-run: emails are printed by the server, not delivered)")
    admin.post(f"/campaigns/{cid}/send", headers=origin).raise_for_status()
    for _ in range(120):
        status = db.execute("SELECT status FROM campaign WHERE id=?", (cid,)).fetchone()[0]
        if str(status).lower() == "sent":
            break
        time.sleep(0.5)
    targets = db.execute(
        "SELECT t.id, t.token, t.sent_at, u.department FROM target t JOIN user u ON u.id=t.user_id "
        "WHERE t.campaign_id=?", (cid,)).fetchall()
    delivered = [t for t in targets if t["sent_at"]]
    print(f"    {len(delivered)} delivered, {len(targets) - len(delivered)} skipped (no consent)")

    pub = httpx.Client(base_url=args.base, follow_redirects=False, timeout=30)
    tally: Counter[str] = Counter()

    def hit(method: str, path: str, ua: str, ip: str, extra: dict | None = None) -> None:
        h = {"User-Agent": ua, "X-Forwarded-For": ip, **(extra or {})}
        pub.request(method, path, headers=h)

    step("Mail gateway link-scanning (inside the scanner window)")
    for t in delivered:
        if random.random() < BASE["scan"]:
            ip, ua = scanner_ip(), random.choice(SCANNER_UAS)
            if random.random() < 0.5:
                hit("HEAD", f"/t/click/{t['token']}", ua, ip)
                tally["scanner HEAD probe"] += 1
            hit("GET", f"/t/click/{t['token']}", ua, ip,
                {"Sec-Purpose": "prefetch"} if random.random() < 0.2 else None)
            tally["scanner GET fetch"] += 1
            # Gateways fetch every link, including "Report this email": the
            # platform must not count these as reports.
            hit("GET", f"/t/report/{t['token']}", ua, ip)
            tally["scanner fetch of report link"] += 1

    wait = args.window + 2
    step(f"Waiting {wait}s so human activity falls outside the scanner window")
    time.sleep(wait)

    modules = db.execute("SELECT id, slug FROM trainingmodule").fetchall()
    questions = {m["slug"]: db.execute(
        "SELECT id, correct_index FROM trainingquestion WHERE module_id=?", (m["id"],)).fetchall()
        for m in modules}

    step("Staff opening, clicking, reporting and training")
    for t in delivered:
        dept = t["department"]
        tok = t["token"]
        mobile = random.random() < BASE["mobile"]
        ua = random.choice(MOBILE_UAS if mobile else DESKTOP_UAS)
        ip = office_ip()
        p_click = BASE["click"] * DEPT_CLICK.get(dept, 1.0)
        p_report = BASE["report"] * DEPT_REPORT.get(dept, 1.0)

        opened = random.random() < BASE["open"]
        if opened:
            hit("GET", f"/t/open/{tok}.png", random.choice(MAIL_CLIENT_UAS), ip)
            tally["email opened"] += 1

        clicked = opened and random.random() < p_click / BASE["open"]
        if clicked:
            hit("GET", f"/t/click/{tok}", ua, ip)
            if random.random() >= BASE["nojs"]:
                hit("POST", f"/t/confirm/{tok}", ua, ip)
                tally["human click (JS confirmed)"] += 1
            else:
                tally["human click (JS blocked)"] += 1
            if mobile:
                tally["  of which on mobile"] += 1

        # Some report without clicking; a few clickers realise and report after.
        if (not clicked and random.random() < p_report) or (clicked and random.random() < 0.15):
            hit("GET", f"/t/report/{tok}", ua, ip)           # confirmation page
            pub.post(f"/t/report/{tok}", data={"js": "1"},     # its auto-submit
                     headers={"User-Agent": ua, "X-Forwarded-For": ip})
            tally["reported"] += 1

        if clicked and modules and random.random() < BASE["quiz"]:
            m = random.choice(modules)
            form = {}
            for q in questions[m["slug"]]:
                right = random.random() < 0.75
                form[f"q{q['id']}"] = str(q["correct_index"] if right else (q["correct_index"] + 1) % 4)
            pub.post(f"/t/training/{tok}/{m['slug']}/quiz", data=form,
                     headers={"User-Agent": ua, "X-Forwarded-For": ip, "Origin": args.base})
            tally["training quiz taken"] += 1

    step("Result (simulated behaviour)")
    for k, v in tally.items():
        print(f"    {k:<30} {v}")

    verdicts = db.execute(
        "SELECT lower(verdict), COUNT(*) FROM event WHERE campaign_id=? AND lower(type)='click' "
        "GROUP BY lower(verdict)",
        (cid,)).fetchall()
    step("What the platform recorded for clicks")
    for v, n in verdicts:
        print(f"    {v:<10} {n}")

    print(f"\nOpen {args.base}/campaigns/{cid}  (login {args.user} / {args.password})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
