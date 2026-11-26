# Deploying PhishGuard

This guide takes PhishGuard from a fresh Linux server to a live HTTPS instance
that sends real (authorised) drill emails. It uses `docker-compose.prod.yml`:
Caddy terminates TLS with an automatically renewed certificate and is the only
thing exposed to the network; the app runs on an internal Docker network.

```
internet ──443──▶ Caddy (TLS, HTTP/3) ──internal network──▶ PhishGuard (uvicorn) ──▶ SQLite volume
```

## Before you start

- [ ] **Written authorisation** from the organisation for every drill you will run,
      and a list of consenting recipients. The app refuses to email anyone not
      marked as consenting, but authorisation is your responsibility.
- [ ] A Linux host with Docker Engine and the Compose plugin.
- [ ] A domain name (e.g. `phish.example.com`) whose DNS A/AAAA record points at
      the host. Ports **80** and **443** must be reachable from the internet so
      Caddy can obtain the certificate.
- [ ] An SMTP account for sending (a transactional provider or the organisation's
      relay). Coordinate with the mail team: allow-list the sending domain/IP so
      drill emails are delivered, and tell them about the scanner-click detection.

## 1. Configure

```bash
git clone <your fork> phishguard && cd phishguard
cp .env.example .env
```

Edit `.env`:

| Variable | Value |
| --- | --- |
| `ENV` | `prod` (forced by the compose file anyway) |
| `DOMAIN` | `phish.example.com` |
| `BASE_URL` | `https://phish.example.com`: tracked links point here |
| `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | a long, unique password from a password manager |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | your mail provider |
| `ALLOWED_RECIPIENT_DOMAINS` | the organisation's domain(s), e.g. `corp.example`: real sends to any other domain are refused |
| `RETENTION_DAYS` | how long to keep click evidence, e.g. `180` |

In prod the app **refuses to start** if `SECRET_KEY`, `ADMIN_PASSWORD` or SMTP is
missing, so a misconfiguration fails loudly instead of running insecurely.
`TRUSTED_PROXIES` and `DATABASE_URL` are set by the compose file; leave them out.

`chmod 600 .env`: it holds credentials. It is git-ignored.

## 2. Start

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # both services "healthy"
curl -fsS https://phish.example.com/health          # {"status":"ok"}
```

The container runs `python -m app.migrate` before serving, so a fresh volume
gets the full schema and an existing one is upgraded in place.

## 3. Verify (5 minutes)

1. Open `https://phish.example.com`, which redirects to the login page. Log in.
2. **Users**: add yourself (a mailbox you control) and tick *consented*.
3. **Phishing**: create a campaign from a drill template, target yourself, send.
4. In the email, open it, then click the link in a normal browser. The campaign
   should show one **human** click. If your mail gateway rewrites links you will
   also see **scanner** clicks: that is the click-accuracy engine working.
5. Click *Take the training* on the landing page and pass the quiz; your result
   appears under **Training** for that person.

## Hardening in this setup

- TLS everywhere (HSTS on), HTTP redirected to HTTPS, HTTP/3 enabled.
- App container: non-root user, read-only root filesystem, all Linux
  capabilities dropped, `no-new-privileges`, no published ports.
- Client IPs: Caddy overwrites `X-Forwarded-For`; the app trusts it only from
  Caddy's fixed internal address, so the evidence log can't be spoofed.
- `/docs`, `/redoc` and `/openapi.json` are disabled in prod and blocked at the edge.
- Admin session: signed `__Host-` cookie, `Secure`, `SameSite=Lax`, 8-hour
  absolute lifetime, rotated on login and revoked on logout; CSRF tokens on every
  form; login locks for 15 minutes after 5 failures.
- Caddy access logs are off: the app already keeps the evidence it needs, and a
  second copy would sit outside `RETENTION_DAYS` and right-to-erasure.

## Operations

**Backups**: the whole state is one SQLite file in the `phishguard-data` volume.
Use SQLite's online backup so a running app is captured consistently:

```bash
docker compose -f docker-compose.prod.yml exec web \
  python -c "import sqlite3; s=sqlite3.connect('/data/phishing.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose -f docker-compose.prod.yml cp web:/data/backup.db ./phishguard-$(date +%F).db
```

Store backups encrypted: they contain staff names, emails and click evidence.

**Retention purge**: run daily from the host's cron:

```cron
15 3 * * * cd /srv/phishguard && docker compose -f docker-compose.prod.yml exec -T web python -m app.maintenance
```

**Right to erasure** (GDPR Art. 17 / PDPA): use the *Erase* button on the Users
tab, or `docker compose -f docker-compose.prod.yml exec web python -m app.maintenance erase person@corp.example`.

**Upgrades**: `git pull && docker compose -f docker-compose.prod.yml up -d --build`.
Take a backup first; migrations run automatically on start.

**Logs**: `docker compose -f docker-compose.prod.yml logs -f web`. Every response
carries an `X-Request-ID` that also appears in the log line, and admin actions
are recorded in the audit log shown on the Reports tab.

## Scaling notes

The shipped setup runs **one** uvicorn worker on SQLite (WAL mode), which is
plenty for drills against a few thousand staff. Login throttling and session
revocation are held in process memory by design. If you need several workers or
hosts, move to Postgres (`DATABASE_URL=postgresql+psycopg://...`) and a shared
store for those two pieces of state first.

## Public demo on AWS (one command)

`deploy/aws/` stands up a public, read-it-yourself demo on a single small EC2
instance, for portfolios and evaluations. It runs with **`DEMO_MODE`**:

- **No email can ever be sent.** Dry-run is forced, and the app refuses to start
  if SMTP is configured.
- The sign-in page shows the shared demo login, and every page carries a
  "Public demo" badge.
- Login throttling is per IP, so nobody can lock the shared account.
- Data is fictional and **resets nightly** (`scripts/demo_reset.py` replays
  three drills through the drill simulator).

```bash
aws login                                   # or any configured AWS credentials
DEMO_PASSWORD='pick-a-demo-password' ALERT_EMAIL=you@example.com deploy/aws/deploy.sh
deploy/aws/redeploy.sh                      # ship the current commit
deploy/aws/teardown.sh                      # delete everything (stops all charges)
```

What the CloudFormation stack (`deploy/aws/phishguard-demo.yaml`) creates:

| Resource | Notes |
| --- | --- |
| EC2 `t4g.micro` (ARM, Ubuntu 24.04) | Encrypted gp3 disk, IMDSv2 only, 1 GB swap |
| Elastic IP | Gives a stable free hostname: `<ip-with-dashes>.sslip.io`, so Caddy can get a real TLS certificate without buying a domain |
| Security group | Inbound 80/443 only. **No SSH port**: admin access is through SSM Session Manager (`aws ssm start-session --target <instance-id>`) |
| IAM role | SSM core plus read access to the one code tarball |
| AWS Budgets alert (optional) | Emails at 80% of the monthly budget and when the forecast exceeds it |

The code reaches the instance as a `git archive` of the current commit in a
private S3 bucket, so no repository credentials live on the server. The
instance generates its own `SECRET_KEY` on first boot. First boot takes about
10 minutes: it installs Docker, builds the image, obtains the certificate and
seeds the demo data.

Approximate cost: about US$10 a month (instance, public IPv4 and disk), which
AWS Free Tier credits cover.
