"""Allowed values (enums) shared by the models, services and generator.

Defined once here so every layer uses the same spelling.
"""
from enum import StrEnum

from sqlalchemy import CheckConstraint


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# Used to compare risk levels: a requirement applies when customer rank >= min rank.
RISK_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


class CustomerStatus(StrEnum):
    PROSPECT = "PROSPECT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class DocumentStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class VerificationResult(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class ReviewStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    OVERDUE = "OVERDUE"


class AlertType(StrEnum):
    EXPIRY_UPCOMING = "EXPIRY_UPCOMING"
    DOCUMENT_EXPIRED = "DOCUMENT_EXPIRED"
    REVIEW_OVERDUE = "REVIEW_OVERDUE"
    EXPIRED_MARKED_VALID = "EXPIRED_MARKED_VALID"
    APPROVED_MISSING_EVIDENCE = "APPROVED_MISSING_EVIDENCE"
    OWNERSHIP_OVER_100 = "OWNERSHIP_OVER_100"
    REVIEW_CLOSED_NO_RESOLUTION = "REVIEW_CLOSED_NO_RESOLUTION"
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"


class AlertSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


def values_check(column: str, enum_cls: type[StrEnum], name: str) -> CheckConstraint:
    """Build a CHECK constraint like: status IN ('A', 'B', 'C').

    A new CheckConstraint object is built on every call because SQLAlchemy
    does not allow one constraint object to be shared between tables.
    """
    allowed = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)
