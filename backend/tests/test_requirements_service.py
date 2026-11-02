"""Tests for the 'which requirements apply' rule."""
from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database import Base
from app.seed_reference import seed_reference_data
from app.services.requirements import applicable_requirements, is_effective, load_requirement_specs
from generator.documents import specs_from_seed_data

AS_OF = date(2026, 10, 22)

# Hand-counted in the Phase 2C design table.
EXPECTED_MANDATORY = {
    ("INDIVIDUAL", "LOW"): 2, ("INDIVIDUAL", "MEDIUM"): 3, ("INDIVIDUAL", "HIGH"): 5,
    ("SOLE_PROPRIETOR", "LOW"): 3, ("SOLE_PROPRIETOR", "MEDIUM"): 4, ("SOLE_PROPRIETOR", "HIGH"): 6,
    ("COMPANY", "LOW"): 4, ("COMPANY", "MEDIUM"): 7, ("COMPANY", "HIGH"): 9,
    ("TRUST", "LOW"): 3, ("TRUST", "MEDIUM"): 5, ("TRUST", "HIGH"): 8,
}


@pytest.mark.parametrize("key,expected", list(EXPECTED_MANDATORY.items()))
def test_mandatory_counts_match_design_table(key, expected):
    customer_type, risk = key
    specs = specs_from_seed_data()
    result = applicable_requirements(customer_type, risk, specs, AS_OF, mandatory_only=True)
    assert len(result) == expected


def test_optional_requirement_only_when_mandatory_not_required():
    specs = specs_from_seed_data()
    all_items = applicable_requirements("INDIVIDUAL", "MEDIUM", specs, AS_OF)
    mandatory = applicable_requirements("INDIVIDUAL", "MEDIUM", specs, AS_OF, mandatory_only=True)
    assert len(all_items) == len(mandatory) + 1
    assert "Employment or income proof" in {s.name for s in all_items}


def test_result_is_sorted_by_id():
    result = applicable_requirements("COMPANY", "HIGH", specs_from_seed_data(), AS_OF)
    ids = [s.requirement_id for s in result]
    assert ids == sorted(ids)


def test_requirement_not_yet_in_force_is_excluded():
    specs = [replace(s, effective_from=date(2027, 1, 1)) for s in specs_from_seed_data()]
    assert applicable_requirements("INDIVIDUAL", "HIGH", specs, AS_OF) == []


def test_requirement_that_has_ended_is_excluded():
    spec = replace(specs_from_seed_data()[0], effective_to=date(2026, 6, 30))
    assert not is_effective(spec, AS_OF)
    assert is_effective(spec, date(2026, 6, 30))   # last day still counts


def test_unknown_risk_level_is_rejected():
    with pytest.raises(ValueError):
        applicable_requirements("INDIVIDUAL", "EXTREME", specs_from_seed_data(), AS_OF)


def test_unknown_customer_type_gets_nothing():
    assert applicable_requirements("ALIEN", "HIGH", specs_from_seed_data(), AS_OF) == []


def test_database_specs_equal_seed_specs():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_reference_data(session)
        from_db = load_requirement_specs(session)
    assert from_db == specs_from_seed_data()
