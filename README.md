# Phishing Awareness Platform

A self-hosted phishing-simulation and security-awareness tool — a small, honest
take on what KnowBe4 does. It runs a phishing drill against a **consenting** test
list, tracks opens / clicks / reports, and — the point of the whole thing —
**tells a real human click apart from an automated scanner click, with evidence.**

> Portfolio / learning project. Part of my cybersecurity track alongside my Home
> SOC Lab and SME Compliance Toolkit.

## Why click accuracy

This started from a real problem at my internship. A phishing-assessment vendor
reported "1 clicker out of 14 detected clicks" and blamed Outlook / Microsoft
link scanning — but four people admitted to my face they had really clicked.
Nobody could cleanly separate a machine click from a human click, so the result
came down to *"trust us."*

Email security gateways (Microsoft SafeLinks, Proofpoint, Barracuda, Mimecast…)
and link-preview bots routinely **fetch every link in an email before a human
ever sees it**, which inflates click counts. This tool logs the raw IP,
User-Agent and timing on every click and classifies it:

| Signal | Verdict |
|---|---|
| Landing page **ran JavaScript** (scanners don't) | **human** (decisive) |
| Prefetch/preview header (`Sec-Purpose: prefetch`, …) | scanner |
| User-Agent matches a known scanner/bot | scanner |
| `HEAD` request (a probe, not a visit) | scanner |
| Empty User-Agent | scanner |
| Click within the scan window, no JS confirm yet | unknown (held) |
| Browser UA, no red flags, outside the window | human |

The logic lives in [`app/detection.py`](app/detection.py) as a pure, unit-tested
function. Every verdict ships with a human-readable reason shown in the dashboard,
so a disputed click can be answered with evidence instead of "trust us".

## Ethics (non-negotiable)

This is a dual-use tool. **Only run it against your own test accounts or with
written authorisation.** Never phish real people without explicit permission.
The sender refuses any recipient not marked as consenting.

## Tabs

- **Dashboard** — KPIs across everything (users, campaigns, human click rate,
  scanner clicks filtered, reports) and recent activity.
- **Phishing** — create campaigns, pick recipients from the user directory, send
  the drill, and see each campaign's evidence log.
- **Training** — micro-lessons + short quizzes (seeded on first run). Shown after a
  click, but anyone can take them; results are tracked.
- **Users** — the global people directory, with the per-person consent gate.
  One-click **"Generate staff"** creates a batch of realistic random people for
  testing. **Groups** let you bucket staff (e.g. "New staff", "Failed phishing —
  Nov"): create a group, bulk-assign checked users to it, and filter the directory
  by group. A campaign can then target a whole group at once.
- **Reports** — per-person risk score across all campaigns, the full evidence log,
  and a one-click CSV export.

## Stack

Python · FastAPI · SQLModel (SQLite) · Jinja2. No build step. Training content is
seeded automatically on first run.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # defaults work out of the box (dry-run mode)
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

With no SMTP configured the app runs in **dry-run mode**: "sending" a drill prints
each email and its tracking URLs to the console instead of mailing anyone. To send
for real, fill in the `SMTP_*` values in `.env`.

### Try the whole flow (dry-run)

1. Create a campaign on the dashboard.
2. Add a recipient (yourself / a test address).
3. Click **Send drill** — the tracking URLs print to the console.
4. Paste a recipient's click URL into a browser → you land on the awareness page,
   and the dashboard logs a **human** click (your browser ran the JS beacon).
5. `curl` the same URL → logged as a **scanner** click (`curl` User-Agent, no JS).

That side-by-side is the demo: the browser and the scanner hit the identical link,
and the platform tells them apart.

## Tests

```bash
pip install pytest
pytest
```

`tests/test_detection.py` covers the engine, including the exact case that
started this: a scanner click must never be counted as a human click, and a real
browser must be.

## Roadmap

- **MVP (done):** campaigns, tracked send, open pixel, click classification, JS
  confirm, report endpoint, evidence-log dashboard.
- **v2 (done):** five-tab UI (Dashboard / Phishing / Training / Users / Reports),
  global user directory, awareness micro-lessons + quizzes, per-person risk score,
  CSV evidence export.
- **v2.1 (done):** random staff generator, staff groups (create / assign / filter),
  and group-based campaign targeting.
- **v2.2 (done):** professional UI refresh — branded "PhishGuard" sidebar with icons,
  topbar with page titles, refined dark theme, elevated cards, better tables/forms.
- **Next:** CSV *import* of users, scheduled campaigns, email-template library, a
  Flutter admin app.
