"""Hub settings, read from SECQA_* environment variables (or a .env file)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SECQA_", env_file=".env", extra="ignore")

    data_dir: Path = Path(".secqa-data")
    database_url: str | None = None
    # When set, every /api request must send `Authorization: Bearer <token>`.
    api_token: str | None = None
    cors_origins: list[str] = []

    # Days to resolve a defect, by severity. Drives `due_at` and SLA breach stats.
    sla_critical_days: int = 7
    sla_high_days: int = 30
    sla_medium_days: int = 90
    sla_low_days: int = 180

    # Relative degradation vs. baseline that counts as a performance regression (0.10 = 10 %).
    perf_regression_tolerance: float = 0.10

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'secqa.db').resolve()}"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    def sla_days(self, severity: str) -> int | None:
        return {
            "critical": self.sla_critical_days,
            "high": self.sla_high_days,
            "medium": self.sla_medium_days,
            "low": self.sla_low_days,
        }.get(severity)


@lru_cache
def get_settings() -> Settings:
    return Settings()
