"""Tests for step 3B: customers, business profiles and risk ratings."""
import re
from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.database import Base
from app.models import BusinessProfile, Customer, RiskRating
from app.seed_reference import seed_reference_data
from app.services.risk import risk_level_for_score
from generator.customers import (
    generate_customers, load_customers, status_counts, type_counts,
)
from generator.db_utils import clear_generated_data

BUSINESS_TYPES = {"COMPANY", "TRUST"}


@pytest.fixture(scope="module")
def full():
    """The real 8,000-customer dataset, generated once for this file."""
    return generate_customers()


@pytest.fixture(scope="module")
def small():
    return generate_customers(n_customers=400, n_business=50)


# ---------- volumes and mix ----------

def test_full_volume_matches_challenge(full):
    assert len(full.customers) == 8000
    assert len(full.business_profiles) == 1000


def test_type_counts_are_exact():
    assert type_counts(8000, 1000) == {
        "INDIVIDUAL": 6000, "SOLE_PROPRIETOR": 1000, "COMPANY": 850, "TRUST": 150,
    }
    assert sum(type_counts(400, 50).values()) == 400


def test_status_counts_are_exact():
    assert status_counts(8000) == {
        "APPROVED": 4000, "UNDER_REVIEW": 2000, "PROSPECT": 1400, "SUSPENDED": 300, "CLOSED": 300,
    }


def test_generated_types_and_statuses_match_quotas(full):
    assert dict(Counter(c["customer_type_id"] for c in full.customers)) == type_counts(8000, 1000)
    assert dict(Counter(c["status"] for c in full.customers)) == status_counts(8000)


def test_invalid_business_count_is_rejected():
    with pytest.raises(ValueError):
        type_counts(100, 101)


# ---------- ids and customer rules ----------

def test_ids_are_unique_sequential_and_formatted(full):
    ids = [c["customer_id"] for c in full.customers]
    assert ids == [f"CUS-{n:06d}" for n in range(1, 8001)]
    assert all(re.fullmatch(r"CUS-\d{6}", i) for i in ids)


def test_individuals_have_dob_and_businesses_do_not(full):
    for c in full.customers:
        if c["customer_type_id"] in BUSINESS_TYPES:
            assert c["date_of_birth"] is None
        else:
            age_days = (settings.as_of_date - c["date_of_birth"]).days
            assert 21 * 365 <= age_days <= 80 * 365


def test_dates_are_ordered_and_not_in_the_future(full):
    for c in full.customers:
        assert c["created_at"] <= settings.as_of_date
        if c["onboarded_at"] is not None:
            assert c["onboarded_at"] >= c["created_at"]
            assert c["onboarded_at"] <= settings.as_of_date


def test_onboarded_only_for_approved_suspended_closed(full):
    for c in full.customers:
        expected = c["status"] in {"APPROVED", "SUSPENDED", "CLOSED"}
        assert (c["onboarded_at"] is not None) == expected


def test_emails_use_safe_example_domains(full):
    assert all(c["email"].split("@")[1].startswith("example.") for c in full.customers)


# ---------- business profiles (1:1 optional) ----------

def test_exactly_the_business_customers_have_a_profile(full):
    business_ids = {c["customer_id"] for c in full.customers if c["customer_type_id"] in BUSINESS_TYPES}
    profile_ids = [p["customer_id"] for p in full.business_profiles]
    assert set(profile_ids) == business_ids
    assert len(profile_ids) == len(set(profile_ids))  # at most one each


def test_registration_numbers_unique_and_incorporated_before_customer_created(full):
    by_id = {c["customer_id"]: c for c in full.customers}
    regs = [p["registration_number"] for p in full.business_profiles]
    assert len(regs) == len(set(regs))
    for p in full.business_profiles:
        assert p["incorporation_date"] < by_id[p["customer_id"]]["created_at"]


# ---------- risk ratings ----------

def test_every_customer_has_exactly_one_current_rating(full):
    current = Counter(r["customer_id"] for r in full.risk_ratings if r["effective_to"] is None)
    assert set(current) == {c["customer_id"] for c in full.customers}
    assert set(current.values()) == {1}


def test_rating_level_always_matches_score_rule(full):
    for r in full.risk_ratings:
        assert r["level"] == risk_level_for_score(r["score"])
        assert 0 <= r["score"] <= 100


def test_rating_history_is_ordered_and_contiguous(full):
    history = {}
    for r in full.risk_ratings:
        history.setdefault(r["customer_id"], []).append(r)
    for customer_id, rows in history.items():
        rows.sort(key=lambda r: r["effective_from"])
        assert len(rows) in (1, 2)
        for earlier, later in zip(rows, rows[1:]):
            assert earlier["effective_to"] == later["effective_from"] - timedelta(days=1)
            assert earlier["effective_to"] >= earlier["effective_from"]
        assert rows[-1]["effective_to"] is None


def test_first_rating_starts_when_customer_was_created(full):
    created = {c["customer_id"]: c["created_at"] for c in full.customers}
    first = {}
    for r in sorted(full.risk_ratings, key=lambda r: r["effective_from"]):
        first.setdefault(r["customer_id"], r)
    assert all(first[cid]["effective_from"] == created[cid] for cid in created)


def test_current_risk_mix_has_all_three_levels(full):
    mix = Counter(r["level"] for r in full.risk_ratings if r["effective_to"] is None)
    total = sum(mix.values())
    assert all(mix[level] / total > 0.05 for level in ("LOW", "MEDIUM", "HIGH"))
    assert mix["HIGH"] < mix["MEDIUM"]


# ---------- determinism ----------

def test_same_seed_gives_identical_data():
    a = generate_customers(n_customers=300, n_business=40)
    b = generate_customers(n_customers=300, n_business=40)
    assert a == b


def test_different_seed_gives_different_data():
    a = generate_customers(n_customers=300, n_business=40, seed=1)
    b = generate_customers(n_customers=300, n_business=40, seed=2)
    assert a != b


# ---------- loading into a real (in-memory) database ----------

@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_reference_data(s)
        yield s
    engine.dispose()


def test_load_inserts_all_rows_with_valid_foreign_keys(session, small):
    counts = load_customers(session, small)
    assert counts == {
        "customer": 400, "business_profile": 50, "risk_rating": len(small.risk_ratings),
    }
    assert session.scalar(select(func.count()).select_from(Customer)) == 400
    assert session.scalar(select(func.count()).select_from(BusinessProfile)) == 50
    # no orphans: every rating and profile joins to a customer
    orphans = session.scalar(
        select(func.count()).select_from(RiskRating)
        .outerjoin(Customer, Customer.customer_id == RiskRating.customer_id)
        .where(Customer.customer_id.is_(None))
    )
    assert orphans == 0


def test_clear_then_reload_gives_the_same_row_counts(session, small):
    load_customers(session, small)
    deleted = clear_generated_data(session)
    assert deleted["customer"] == 400
    assert session.scalar(select(func.count()).select_from(Customer)) == 0
    load_customers(session, small)
    assert session.scalar(select(func.count()).select_from(Customer)) == 400


def test_clear_keeps_master_data(session, small):
    from app.models import CustomerType, KYCRequirement
    load_customers(session, small)
    clear_generated_data(session)
    assert session.scalar(select(func.count()).select_from(CustomerType)) == 4
    assert session.scalar(select(func.count()).select_from(KYCRequirement)) == 15
