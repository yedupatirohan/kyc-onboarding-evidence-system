"""Tests for the master data: counts, IDs, idempotency and the risk-based rules."""
import re
from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database import Base
from app.enums import RISK_RANK
from app.models import CustomerType, KYCRequirement, customer_type_requirement
from app.seed_reference import (
    REQUIREMENTS,
    SEED_EFFECTIVE_FROM,
    requirement_id,
    seed_reference_data,
)

# Expected number of MANDATORY items per (customer type, risk level).
# Worked out by hand from the requirement table in the design.
EXPECTED_MANDATORY = {
    ("INDIVIDUAL", "LOW"): 2, ("INDIVIDUAL", "MEDIUM"): 3, ("INDIVIDUAL", "HIGH"): 5,
    ("SOLE_PROPRIETOR", "LOW"): 3, ("SOLE_PROPRIETOR", "MEDIUM"): 4, ("SOLE_PROPRIETOR", "HIGH"): 6,
    ("COMPANY", "LOW"): 4, ("COMPANY", "MEDIUM"): 7, ("COMPANY", "HIGH"): 9,
    ("TRUST", "LOW"): 3, ("TRUST", "MEDIUM"): 5, ("TRUST", "HIGH"): 8,
}


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_reference_data(s)
        yield s
    engine.dispose()


def mandatory_count(session, type_id, risk):
    """Count mandatory requirements that apply to this type at this risk level."""
    customer_type = session.get(CustomerType, type_id)
    return sum(
        1
        for r in customer_type.requirements
        if r.is_mandatory and RISK_RANK[r.min_risk_level] <= RISK_RANK[risk]
    )


def test_row_counts(session):
    assert session.scalar(select(func.count()).select_from(CustomerType)) == 4
    assert session.scalar(select(func.count()).select_from(KYCRequirement)) == 15
    assert session.scalar(select(func.count()).select_from(customer_type_requirement)) == 29


def test_requirement_ids_are_sequential_and_formatted(session):
    ids = sorted(session.scalars(select(KYCRequirement.requirement_id)))
    assert ids == [requirement_id(i) for i in range(1, len(REQUIREMENTS) + 1)]
    assert all(re.fullmatch(r"KYC-2026-\d{6}", i) for i in ids)
    assert ids[0] == "KYC-2026-000001"


def test_seeding_twice_creates_nothing_new(session):
    second_run = seed_reference_data(session)
    assert second_run == {"customer_types": 0, "requirements": 0, "links": 0}
    assert session.scalar(select(func.count()).select_from(KYCRequirement)) == 15
    assert session.scalar(select(func.count()).select_from(customer_type_requirement)) == 29


def test_business_flags(session):
    flags = {t.customer_type_id: t.is_business for t in session.scalars(select(CustomerType))}
    assert flags == {
        "INDIVIDUAL": False, "SOLE_PROPRIETOR": False, "COMPANY": True, "TRUST": True,
    }


def test_every_requirement_applies_to_at_least_one_type(session):
    for requirement in session.scalars(select(KYCRequirement)):
        assert len(requirement.customer_types) >= 1, requirement.name


@pytest.mark.parametrize(
    "type_id,risk,expected",
    [(t, r, n) for (t, r), n in EXPECTED_MANDATORY.items()],
)
def test_mandatory_counts_by_type_and_risk(session, type_id, risk, expected):
    assert mandatory_count(session, type_id, risk) == expected


def test_higher_risk_never_needs_less_evidence(session):
    for type_id in ("INDIVIDUAL", "SOLE_PROPRIETOR", "COMPANY", "TRUST"):
        low = mandatory_count(session, type_id, "LOW")
        medium = mandatory_count(session, type_id, "MEDIUM")
        high = mandatory_count(session, type_id, "HIGH")
        assert low <= medium <= high, type_id


def test_effective_dates_and_validity(session):
    for requirement in session.scalars(select(KYCRequirement)):
        assert requirement.effective_from == SEED_EFFECTIVE_FROM == date(2026, 1, 1)
        assert requirement.effective_to is None
        assert requirement.validity_months is None or requirement.validity_months > 0
