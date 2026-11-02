"""Deterministic, immutable ID builders and their format patterns.

Every ID is built from numbers (never from random text), so the same inputs
always give the same ID. Numbers are zero-padded so IDs sort correctly as text.
"""
import re

# Largest counters each format can hold.
MAX_6_DIGIT = 999_999
MAX_DOC_SEQ = 999
MAX_RATING_SEQ = 999
MAX_VERIFICATION_SEQ = 99
MAX_LINK_SEQ = 99

# Full-match patterns, used by tests and by the Phase 4 validation script.
PATTERNS = {
    "customer": re.compile(r"CUS-\d{6}"),
    "requirement": re.compile(r"KYC-2026-\d{6}"),
    "document": re.compile(r"DOC-CUS-\d{6}-\d{3}"),
    "review": re.compile(r"REV-CUS-\d{6}-\d{4}"),
    "alert": re.compile(r"ALT-\d{4}-\d{6}"),
    "risk_rating": re.compile(r"RSK-CUS-\d{6}-\d{3}"),
    "verification": re.compile(r"VER-CUS-\d{6}-\d{3}-\d{2}"),
    "owner": re.compile(r"BO-\d{6}"),
    "ownership_link": re.compile(r"OWN-CUS-\d{6}-\d{2}"),
    "audit_event": re.compile(r"AUD-\d{4}-\d{6}"),
}


def _check(value: int, high: int, label: str, low: int = 1) -> int:
    """Return value if it is an int within [low, high], otherwise raise ValueError."""
    if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
        raise ValueError(f"{label} must be an integer from {low} to {high}, got {value!r}")
    return value


def customer_id(number: int) -> str:
    """1 -> 'CUS-000001'."""
    return f"CUS-{_check(number, MAX_6_DIGIT, 'customer number'):06d}"


def document_id(customer_number: int, sequence: int) -> str:
    """(1, 1) -> 'DOC-CUS-000001-001'."""
    return f"DOC-{customer_id(customer_number)}-{_check(sequence, MAX_DOC_SEQ, 'document sequence'):03d}"


def review_id(customer_number: int, year: int) -> str:
    """(1, 2026) -> 'REV-CUS-000001-2026'."""
    return f"REV-{customer_id(customer_number)}-{_check(year, 9999, 'year', low=1000):04d}"


def alert_id(year: int, sequence: int) -> str:
    """(2026, 1) -> 'ALT-2026-000001'."""
    return f"ALT-{_check(year, 9999, 'year', low=1000):04d}-{_check(sequence, MAX_6_DIGIT, 'alert sequence'):06d}"


def risk_rating_id(customer_number: int, sequence: int) -> str:
    """(1, 1) -> 'RSK-CUS-000001-001'."""
    return f"RSK-{customer_id(customer_number)}-{_check(sequence, MAX_RATING_SEQ, 'rating sequence'):03d}"


def verification_id(customer_number: int, document_sequence: int, sequence: int) -> str:
    """(1, 1, 1) -> 'VER-CUS-000001-001-01'."""
    return (
        f"VER-{customer_id(customer_number)}-"
        f"{_check(document_sequence, MAX_DOC_SEQ, 'document sequence'):03d}-"
        f"{_check(sequence, MAX_VERIFICATION_SEQ, 'verification sequence'):02d}"
    )


def owner_id(number: int) -> str:
    """1 -> 'BO-000001'."""
    return f"BO-{_check(number, MAX_6_DIGIT, 'owner number'):06d}"


def ownership_link_id(customer_number: int, sequence: int) -> str:
    """(1, 1) -> 'OWN-CUS-000001-01'."""
    return f"OWN-{customer_id(customer_number)}-{_check(sequence, MAX_LINK_SEQ, 'link sequence'):02d}"


def audit_event_id(year: int, sequence: int) -> str:
    """(2026, 1) -> 'AUD-2026-000001'."""
    return f"AUD-{_check(year, 9999, 'year', low=1000):04d}-{_check(sequence, MAX_6_DIGIT, 'audit sequence'):06d}"


def parse_customer_number(value: str) -> int:
    """'CUS-000042' -> 42. Raises ValueError for anything not in the exact format."""
    if not PATTERNS["customer"].fullmatch(value):
        raise ValueError(f"Not a valid customer ID: {value!r}")
    return int(value[4:])
