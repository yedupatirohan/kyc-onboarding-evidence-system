"""Compliance records: reviews, beneficial ownership, alerts and the audit trail."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import AlertSeverity, AlertStatus, AlertType, ReviewStatus, values_check


class ReviewCase(Base):
    __tablename__ = "review_case"

    review_id: Mapped[str] = mapped_column(String(30), primary_key=True)  # REV-CUS-000001-2026
    customer_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("customer.customer_id"), nullable=False, index=True
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default=ReviewStatus.SCHEDULED.value, index=True)
    opened_at: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date)
    # NOTE: no CHECK forcing a resolution when CLOSED. The database must be able to
    # hold that bad state (anomaly #4); the rules layer detects it.
    resolution: Mapped[str | None] = mapped_column(Text)
    closed_by: Mapped[str | None] = mapped_column(String(100))

    __table_args__ = (
        values_check("status", ReviewStatus, "ck_review_case_status"),
        CheckConstraint(
            "closed_at IS NULL OR opened_at IS NULL OR closed_at >= opened_at",
            name="ck_review_case_dates",
        ),
    )

    customer = relationship("Customer", back_populates="review_cases")


class BeneficialOwner(Base):
    __tablename__ = "beneficial_owner"

    owner_id: Mapped[str] = mapped_column(String(12), primary_key=True)  # BO-000001
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(2))

    ownership_links = relationship("OwnershipLink", back_populates="owner")


class OwnershipLink(Base):
    """Bridge (N:M) between a business Customer and a BeneficialOwner, with ownership %."""

    __tablename__ = "ownership_link"

    link_id: Mapped[str] = mapped_column(String(30), primary_key=True)  # OWN-CUS-000001-01
    customer_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("customer.customer_id"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("beneficial_owner.owner_id"), nullable=False, index=True
    )
    ownership_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        # One row can be 0-100%. The SUM across rows cannot be checked here (anomaly #3).
        CheckConstraint("ownership_pct > 0 AND ownership_pct <= 100", name="ck_ownership_pct_range"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_ownership_dates",
        ),
    )

    customer = relationship("Customer", back_populates="ownership_links")
    owner = relationship("BeneficialOwner", back_populates="ownership_links")


class Alert(Base):
    __tablename__ = "alert"

    alert_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # ALT-2026-000001
    customer_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("customer.customer_id"), nullable=False, index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("document.document_id"), index=True
    )  # optional: some alerts are not about a document
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default=AlertStatus.OPEN.value, index=True)
    lead_days: Mapped[int | None] = mapped_column(Integer)  # for expiry alerts: 90 / 60 / 30
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[date] = mapped_column(Date, nullable=False)
    resolved_at: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        values_check("alert_type", AlertType, "ck_alert_type"),
        values_check("severity", AlertSeverity, "ck_alert_severity"),
        values_check("status", AlertStatus, "ck_alert_status"),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= created_at",
            name="ck_alert_dates",
        ),
    )

    customer = relationship("Customer", back_populates="alerts")
    document = relationship("Document", back_populates="alerts")


class AuditEvent(Base):
    """Append-only history of important changes.

    entity_type + entity_id point at ANY table, so there is deliberately no
    foreign key: audit history must outlive the records it describes.
    """

    __tablename__ = "audit_event"

    event_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # AUD-2026-000001
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)  # JSON text
    new_value: Mapped[str | None] = mapped_column(Text)  # JSON text
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (Index("ix_audit_event_entity", "entity_type", "entity_id"),)
