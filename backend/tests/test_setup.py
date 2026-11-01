"""Smoke tests: prove the foundation is configured as the challenge requires."""
from sqlalchemy import text

from app.config import settings
from app.database import engine


def test_seed_and_as_of_date_are_fixed():
    assert settings.seed == 20261022
    assert settings.as_of_date.isoformat() == "2026-10-22"


def test_volumes_match_challenge():
    assert settings.n_customers == 8000
    assert settings.n_business == 1000
    assert settings.n_documents == 20000
    assert settings.n_reviews == 3000


def test_alert_lead_times_parsed_and_sorted():
    assert settings.alert_lead_times == [90, 60, 30]


def test_sqlite_foreign_keys_are_enforced():
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
