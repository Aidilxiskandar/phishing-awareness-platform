# Changelog

All notable changes to PhishGuard are recorded here. Versioning is loosely
semantic.

## [Unreleased]
### Added
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
