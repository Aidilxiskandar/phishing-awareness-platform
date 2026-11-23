"""Application configuration, loaded from environment / .env."""
from __future__ import annotations

import secrets as _secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

# Ephemeral session key used only in dev when SECRET_KEY is unset. Regenerated each
# process start, so dev sessions don't survive a restart (prod must set SECRET_KEY).
_DEV_SECRET = _secrets.token_urlsafe(32)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # --- Training ---
    # Minimum quiz score (percent) that counts as passing a module.
    training_pass_percent: int = 80

    # --- Data retention ---
    # Delete evidence (events) older than this many days. 0 = keep indefinitely.
    retention_days: int = 0

    # --- Infrastructure ---
    # Override the SQLite location / use another DB URL. Empty = default file in repo.
    database_url: str = ""
    # Comma-separated proxy IPs whose X-Forwarded-For header we trust. Empty = none.
    trusted_proxies: str = ""

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    @property
    def dry_run(self) -> bool:
        """No SMTP host configured -> print emails to console instead of sending."""
        return not self.smtp_host.strip()

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
    def allowed_domains(self) -> set[str]:
        return {d.strip().lower() for d in self.allowed_recipient_domains.split(",") if d.strip()}

    def validate_for_runtime(self) -> list[str]:
        """Fatal misconfigurations for the current environment (checked at startup)."""
        problems: list[str] = []
        if self.is_prod:
            if not self.secret_key:
                problems.append("SECRET_KEY must be set in production")
            if not self.admin_password:
                problems.append("ADMIN_PASSWORD must be set in production")
            if self.dry_run:
                problems.append(
                    "SMTP is not configured but ENV=prod — campaigns would silently no-op"
                )
        return problems


settings = Settings()
