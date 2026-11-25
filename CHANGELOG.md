# Changelog

All notable changes to PhishGuard are recorded here. Versioning is loosely
semantic.

## [3.0.0] — 2026-11-25
Production-readiness release. Breaking for operators: logout is now `POST`, the
staff training link moved to `/t/training/{token}/{slug}`, and report links
need a browser confirmation (see Changed).

### Added
- **Scanner-proof reporting**: every drill email carries a per-recipient "Report
  this email" link; a fetch shows a confirmation page and only the browser's
  confirmation records the report (once). Report rate, time-to-report and
  reported-without-clicking metrics; risk score credits clean reports.
- **Detection engine v2**: 45 named scanner families, sandbox-aware rules
  (self-declared automation outranks the JS beacon), obsolete-browser disguises,
  operator-declared scanner networks (`SCANNER_NETWORKS`).
- **Analytics**: trend across campaigns, breakdown by staff group, print-ready
  executive report per campaign with recommendations.
- **Email-template library** with red-flag notes, previews and a campaign picker.
- **Security**: per-session CSRF tokens, login lockout, session rotation and
  server-side revocation, nonce-based CSP, `__Host-` cookie, `no-store` admin pages.
- **Production deployment**: `docker-compose.prod.yml` with Caddy (automatic
  HTTPS, HTTP/3), hardened container, and `docs/DEPLOYMENT.md`.
- **Accessibility and mobile**: WCAG contrast fixes, skip link, landmarks,
  keyboard-scrollable tables, colour-independent verdicts, reduced motion.
- **Quality**: property-based detection tests (Hypothesis), end-to-end drill test,
  a headless-Chrome smoke test that runs in CI, 194 tests at 95% coverage.
- Drill simulator (`scripts/simulate_drill.py`), favicon, README screenshots.

### Changed
- `app/main.py` split into per-area routers (`app/routers/`) and `app/web.py`.
- Training course is the five CISA video modules; legacy text modules retired.
- Logout is `POST` with CSRF; `Referrer-Policy: same-origin`.

### Fixed
- **Staff were sent to the admin login** when they clicked "Take the training"
  after a drill (the training route was admin-only).
- **Every admin form failed in real browsers** (`Origin: null` under
  `Referrer-Policy: no-referrer` failed the CSRF origin check).
- **Report counts were inflated by scanners**: a bare fetch of the report link
  recorded a report.
- **Sandboxes counted as humans**: a scanner-classified JS confirm still upgraded
  the click to human.
- A rejected report re-rendered an auto-submitting page (endless POST loop).
- Evidence-log IPs could be spoofed via the left-most `X-Forwarded-For` entry.
- Two Alembic heads after merging migrations; email-template migration now
  tolerates legacy databases.
- Non-ASCII login input raised a 500 instead of a 401.

### Migration notes
- `python -m app.migrate` (run automatically by the Docker image) applies the new
  migrations: `campaign` template fields and `target.reported_at` (backfilled).
- Old staff training links (`/training/{slug}?token=`) now require admin login;
  links in emails sent before upgrading still record clicks normally.

## [2.5.0] — 2026-11-20
### Added
- **`python -m app.migrate`**: upgrades fresh, Alembic-managed and legacy
  (`create_all`) databases to head; the Docker image runs it on every start and
  now ships the `alembic/` migrations. Compose mounts training videos read-only.
- **Right to erasure** (GDPR Art. 17 / PDPA): per-user Erase action on the Users
  tab and `python -m app.maintenance erase EMAIL`. Anonymises the person across
  users, targets, events (IP/UA), quiz results, groups and audit history; rotates
  tracking tokens; keeps campaign aggregates intact. Alembic migration adds
  `user.erased_at`.
- **Coverage**: 59 → 93 tests, ~74% → ~93% branch coverage (training/quiz
  scoring, video resolution, email preview, group targeting, staff seeding, SMTP
  header-injection, prod config). CI now enforces `fail_under = 85`.
- **Deployment**: multi-stage `Dockerfile` (Python 3.12, non-root, healthcheck),
  `docker-compose.yml` with a persistent SQLite volume, `.dockerignore`, `Makefile`,
  `LICENSE` (MIT + ethical-use notice), and this changelog.

## [2.4.0] — 2026-11-20
### Added
- **Authentication**: deny-by-default admin session (login/logout), CSRF
  same-origin checks, and security headers. Tracking endpoints stay public.
- **Config**: environments (dev/staging/prod), `SECRET_KEY`, admin credentials,
  `DATABASE_URL` override, trusted-proxy list; fail-fast in prod when secrets or
  SMTP are missing.
- **Test harness**: ruff + pytest + coverage, temp-DB fixtures, 44 tests (~73%).
- `/health` endpoint; SQLite WAL + busy_timeout.
### Changed
- **Consent is opt-in**: users and targets default to non-consenting.
- **Send flow**: idempotent and resumable, runs as a background task, records
  per-target state, and re-checks consent live at send time.
- Replaced the deprecated startup hook with a lifespan handler.
### Security
- Escape recipient names in email/preview (XSS) and strip CR/LF (header injection).
- Trust `X-Forwarded-For` only from configured proxies (evidence-log integrity).
- Escape CSV formula injection in the evidence export.

## [2.3.0] — 2026-11-17
### Added
- Enterprise dashboard with inline-SVG charts (phish-prone trend, risk donut,
  engagement funnel, human-vs-scanner split).
- Training video support (local MP4 or YouTube/Vimeo) + a Remotion animation studio.
- Per-recipient email preview that fires no tracking events.

## [2.2.0] — 2026-11-13
### Added
- Five-tab UI, staff groups (create/assign/filter/target), random staff generator.
- Per-person risk scoring and CSV evidence export.

## [2.0.0]
### Added
- Initial public MVP: campaigns, tracked send, the click-accuracy detection engine,
  open/click/report tracking, and the evidence log.
