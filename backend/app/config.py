"""Central settings for the whole project.

Every tunable value (seed, as-of date, lead times, volumes) lives here so the
generator, services, API and tests all read the same source of truth.
"""
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# This file is backend/app/config.py -> parents[1] = backend, parents[2] = project root
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KYC_",                 # env var KYC_SEED -> field "seed"
        env_file=PROJECT_ROOT / ".env",    # optional file; ignored if missing
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Reproducibility
    seed: int = 20261022
    as_of_date: date = date(2026, 10, 22)  # fixed "today" for all calculations

    # Database
    database_url: str = ""                 # empty -> default SQLite file

    # Expiry alert lead times in days, e.g. "90,60,30"
    alert_lead_days: str = "90,60,30"

    # Review frequency (months) by risk level
    review_months_high: int = 6
    review_months_medium: int = 12
    review_months_low: int = 24

    # Baseline volumes required by the challenge
    n_customers: int = 8000
    n_business: int = 1000
    n_documents: int = 20000
    n_reviews: int = 3000

    @property
    def resolved_database_url(self) -> str:
        """Return the configured URL, or the default SQLite file path."""
        if self.database_url:
            return self.database_url
        db_path = PROJECT_ROOT / "data" / "output" / "kyc.db"
        return f"sqlite:///{db_path.as_posix()}"

    @property
    def alert_lead_times(self) -> list[int]:
        """Parse '90,60,30' into [90, 60, 30], largest first, no duplicates."""
        values = {int(x) for x in self.alert_lead_days.split(",") if x.strip()}
        return sorted(values, reverse=True)


@lru_cache
def get_settings() -> Settings:
    """Build settings once and reuse the same object."""
    return Settings()


settings = get_settings()
