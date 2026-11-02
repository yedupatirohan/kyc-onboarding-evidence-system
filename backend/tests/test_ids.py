"""Tests for the ID builders: formats, ranges, sorting and database column fit."""
import pytest

from app.models import Alert, AuditEvent, BeneficialOwner, Customer, Document, OwnershipLink, ReviewCase, RiskRating, Verification
from generator import ids


def test_customer_id_format():
    assert ids.customer_id(1) == "CUS-000001"
    assert ids.customer_id(8000) == "CUS-008000"


def test_document_id_format():
    assert ids.document_id(1, 1) == "DOC-CUS-000001-001"
    assert ids.document_id(8000, 12) == "DOC-CUS-008000-012"


def test_review_id_format():
    assert ids.review_id(1, 2026) == "REV-CUS-000001-2026"


def test_alert_id_format():
    assert ids.alert_id(2026, 1) == "ALT-2026-000001"


def test_other_id_formats():
    assert ids.risk_rating_id(1, 1) == "RSK-CUS-000001-001"
    assert ids.verification_id(1, 1, 1) == "VER-CUS-000001-001-01"
    assert ids.owner_id(1) == "BO-000001"
    assert ids.ownership_link_id(1, 1) == "OWN-CUS-000001-01"
    assert ids.audit_event_id(2026, 1) == "AUD-2026-000001"


def test_every_id_matches_its_pattern():
    samples = {
        "customer": ids.customer_id(123),
        "requirement": "KYC-2026-000001",
        "document": ids.document_id(123, 4),
        "review": ids.review_id(123, 2026),
        "alert": ids.alert_id(2026, 99),
        "risk_rating": ids.risk_rating_id(123, 2),
        "verification": ids.verification_id(123, 4, 2),
        "owner": ids.owner_id(77),
        "ownership_link": ids.ownership_link_id(123, 3),
        "audit_event": ids.audit_event_id(2026, 5),
    }
    assert set(samples) == set(ids.PATTERNS)  # no format left untested
    for name, value in samples.items():
        assert ids.PATTERNS[name].fullmatch(value), f"{name}: {value}"


def test_longest_ids_fit_database_columns():
    """The widest possible ID of each kind must fit the column size from Phase 2B."""
    widest = [
        (Customer.customer_id, ids.customer_id(999_999)),
        (Document.document_id, ids.document_id(999_999, 999)),
        (ReviewCase.review_id, ids.review_id(999_999, 9999)),
        (Alert.alert_id, ids.alert_id(9999, 999_999)),
        (RiskRating.rating_id, ids.risk_rating_id(999_999, 999)),
        (Verification.verification_id, ids.verification_id(999_999, 999, 99)),
        (BeneficialOwner.owner_id, ids.owner_id(999_999)),
        (OwnershipLink.link_id, ids.ownership_link_id(999_999, 99)),
        (AuditEvent.event_id, ids.audit_event_id(9999, 999_999)),
    ]
    for column, value in widest:
        assert len(value) <= column.type.length, f"{column}: {value} is {len(value)} chars"


def test_out_of_range_numbers_are_rejected():
    with pytest.raises(ValueError):
        ids.customer_id(0)
    with pytest.raises(ValueError):
        ids.customer_id(1_000_000)
    with pytest.raises(ValueError):
        ids.document_id(1, 0)
    with pytest.raises(ValueError):
        ids.document_id(1, 1000)
    with pytest.raises(ValueError):
        ids.customer_id("5")  # a string is not a number


def test_parse_customer_number_round_trip():
    for number in (1, 42, 8000, 999_999):
        assert ids.parse_customer_number(ids.customer_id(number)) == number
    with pytest.raises(ValueError):
        ids.parse_customer_number("CUS-42")
    with pytest.raises(ValueError):
        ids.parse_customer_number("cus-000042")


def test_ids_sort_in_numeric_order():
    numbers = list(range(1, 200))
    as_text = sorted(ids.customer_id(n) for n in numbers)
    assert as_text == [ids.customer_id(n) for n in numbers]
