"""Tests that the schema accepts valid rows and the database rejects invalid ones.

Each test uses a fresh in-memory SQLite database, so it never touches kyc.db.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database import Base
from app.models import (
    BeneficialOwner,
    Customer,
    CustomerType,
    Document,
    KYCRequirement,
    OwnershipLink,
    document_requirement_link,
)

CORE_TABLES = {
    "customer_type", "kyc_requirement", "customer", "document", "verification",
    "risk_rating", "review_case", "beneficial_owner", "alert", "audit_event",
}
BRIDGE_TABLES = {"customer_type_requirement", "document_requirement_link", "ownership_link"}


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def make_customer(session, customer_id="CUS-000001", type_id="INDIVIDUAL", is_business=False):
    if session.get(CustomerType, type_id) is None:
        session.add(CustomerType(customer_type_id=type_id, name=type_id.title(), is_business=is_business))
        session.flush()
    session.add(
        Customer(
            customer_id=customer_id, customer_type_id=type_id, full_name="Test Person",
            country_code="IN", status="PROSPECT", created_at=date(2026, 1, 1),
        )
    )
    session.commit()


def make_document(document_id="DOC-CUS-000001-001", issue=date(2026, 1, 1), expiry=date(2030, 1, 1)):
    return Document(
        document_id=document_id, customer_id="CUS-000001", file_name="passport.pdf",
        file_hash="a" * 64, file_size_bytes=1000, issue_date=issue, expiry_date=expiry,
        status="SUBMITTED", submitted_at=date(2026, 1, 2),
    )


def test_all_expected_tables_exist(session):
    names = set(inspect(session.get_bind()).get_table_names())
    assert CORE_TABLES <= names
    assert BRIDGE_TABLES <= names
    assert "business_profile" in names


def test_every_table_has_a_primary_key(session):
    insp = inspect(session.get_bind())
    for name in insp.get_table_names():
        assert insp.get_pk_constraint(name)["constrained_columns"], f"{name} has no primary key"


def test_foreign_key_blocks_orphan_document(session):
    with pytest.raises(IntegrityError):
        session.add(make_document())  # customer CUS-000001 does not exist
        session.commit()


def test_invalid_status_is_rejected(session):
    make_customer(session)
    bad = make_document()
    bad.status = "VALIDISH"
    with pytest.raises(IntegrityError):
        session.add(bad)
        session.commit()


def test_expiry_before_issue_is_rejected(session):
    make_customer(session)
    with pytest.raises(IntegrityError):
        session.add(make_document(issue=date(2026, 6, 1), expiry=date(2026, 1, 1)))
        session.commit()


def test_duplicate_bridge_pair_is_rejected(session):
    make_customer(session)
    session.add(make_document())
    session.add(KYCRequirement(requirement_id="KYC-2026-000001", name="Passport", effective_from=date(2026, 1, 1)))
    session.commit()
    link = {"document_id": "DOC-CUS-000001-001", "requirement_id": "KYC-2026-000001"}
    session.execute(document_requirement_link.insert().values(**link))
    with pytest.raises(IntegrityError):
        session.execute(document_requirement_link.insert().values(**link))


def test_single_ownership_over_100_rejected_but_sum_over_100_allowed(session):
    make_customer(session, "CUS-000001", "COMPANY", True)
    session.add_all([
        BeneficialOwner(owner_id="BO-000001", full_name="Owner A"),
        BeneficialOwner(owner_id="BO-000002", full_name="Owner B"),
    ])
    session.commit()

    # One row of 130% is blocked by the CHECK constraint.
    with pytest.raises(IntegrityError):
        session.add(OwnershipLink(link_id="OWN-X", customer_id="CUS-000001", owner_id="BO-000001",
                                  ownership_pct=Decimal("130.00"), effective_from=date(2026, 1, 1)))
        session.commit()
    session.rollback()

    # 60% + 55% = 115% is accepted: the database cannot see across rows.
    session.add_all([
        OwnershipLink(link_id="OWN-1", customer_id="CUS-000001", owner_id="BO-000001",
                      ownership_pct=Decimal("60.00"), effective_from=date(2026, 1, 1)),
        OwnershipLink(link_id="OWN-2", customer_id="CUS-000001", owner_id="BO-000002",
                      ownership_pct=Decimal("55.00"), effective_from=date(2026, 1, 1)),
    ])
    session.commit()
    total = sum(link.ownership_pct for link in session.scalars(select(OwnershipLink)))
    assert total > 100  # detecting this is the job of the rules layer, built in Phase 4
