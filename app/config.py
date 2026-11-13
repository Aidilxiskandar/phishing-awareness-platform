"""Application configuration, loaded from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    base_url: str = "http://127.0.0.1:8000"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    scanner_time_window_seconds: int = 15

    @property
    def dry_run(self) -> bool:
        """No SMTP host configured -> print emails to console instead of sending."""
        return not self.smtp_host.strip()


settings = Settings()
