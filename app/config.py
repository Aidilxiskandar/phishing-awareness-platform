"""Application configuration, loaded from environment / .env."""
from __future__ import annotations

import secrets as _secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

# Ephemeral session key used only in dev when SECRET_KEY is unset. Regenerated each
# process start, so dev sessions don't survive a restart (prod must set SECRET_KEY).
_DEV_SECRET = _secrets.token_urlsafe(32)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Public demo: forces dry-run (no email can ever be sent), shows the demo
    # login on the sign-in page and a "Public demo" badge, and keys login
    # throttling by IP only so nobody can lock the shared account. Refuses to
    # start if SMTP is configured. See docs/DEPLOYMENT.md "Public demo".
    demo_mode: bool = False

    # Environment: dev | staging | prod. Drives fail-fast checks, cookie security,
    # and whether the API docs are exposed.
    env: str = "dev"

    base_url: str = "http://127.0.0.1:8000"

    # --- Admin authentication ---
    admin_username: str = "admin"
    admin_password: str = ""   # login password; see effective_admin_password
    secret_key: str = ""       # session-cookie signing key; see effective_secret_key

    # --- Email / SMTP ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # Optional recipient domain allowlist (comma-separated). Empty = no restriction.
    allowed_recipient_domains: str = ""

    # --- Detection ---
    scanner_time_window_seconds: int = 15
    # Optional: IP ranges that only ever carry mail-security scanner traffic, as
    # "cidr[=label]" entries separated by commas, e.g.
    #   "203.0.113.0/24=Mimecast EU, 198.51.100.7=Proofpoint"
    # Clicks from them are labelled scanner. Never list a range staff browse
    # through (e.g. a corporate egress proxy). Empty = none.
    scanner_networks: str = ""

    # --- Training ---
    # Minimum quiz score (percent) that counts as passing a module.
    training_pass_percent: int = 80

    # --- Data retention ---
    # Delete evidence (events) older than this many days. 0 = keep indefinitely.
    retention_days: int = 0

    # --- Infrastructure ---
    # Override the SQLite location / use another DB URL. Empty = default file in repo.
    database_url: str = ""
    # Comma-separated proxy IPs/CIDRs whose X-Forwarded-For header we trust. Empty = none.
    trusted_proxies: str = ""

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    @property
    def dry_run(self) -> bool:
        """No SMTP host configured (or demo mode) -> print emails instead of sending."""
        return self.demo_mode or not self.smtp_host.strip()

    @property
    def effective_secret_key(self) -> str:
        return self.secret_key or _DEV_SECRET

    @property
    def effective_admin_password(self) -> str:
        # In dev, fall back to a known default so the app is usable out of the box.
        # In prod this is empty unless set, and validate_for_runtime() refuses to boot.
        return self.admin_password or ("" if self.is_prod else "phishguard-dev")

    @property
    def trusted_proxy_set(self) -> set[str]:
        return {p.strip() for p in self.trusted_proxies.split(",") if p.strip()}

    @property
    def scanner_network_list(self):
        """Parsed SCANNER_NETWORKS (validated at startup by validate_for_runtime)."""
        from app.detection import parse_scanner_networks
        return parse_scanner_networks(self.scanner_networks)

    @property
    def allowed_domains(self) -> set[str]:
        return {d.strip().lower() for d in self.allowed_recipient_domains.split(",") if d.strip()}

    def validate_for_runtime(self) -> list[str]:
        """Fatal misconfigurations for the current environment (checked at startup)."""
        problems: list[str] = []
        try:
            self.scanner_network_list  # noqa: B018 - parse to validate
        except ValueError as exc:
            problems.append(f"SCANNER_NETWORKS is invalid: {exc}")
        if self.demo_mode and self.smtp_host.strip():
            problems.append("DEMO_MODE must not have SMTP configured: a public demo "
                            "must never be able to send email")
        if self.is_prod:
            if not self.secret_key:
                problems.append("SECRET_KEY must be set in production")
            if not self.admin_password:
                problems.append("ADMIN_PASSWORD must be set in production")
            if self.dry_run and not self.demo_mode:
                problems.append(
                    "SMTP is not configured but ENV=prod — campaigns would silently no-op"
                )
        return problems


settings = Settings()
