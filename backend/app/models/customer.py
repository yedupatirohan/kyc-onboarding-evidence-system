"""Customers, their optional business profile (1:1) and risk-rating history."""
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import CustomerStatus, RiskLevel, values_check


class Customer(Base):
    __tablename__ = "customer"

    customer_id: Mapped[str] = mapped_column(String(10), primary_key=True)  # CUS-000001
    customer_type_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("customer_type.customer_type_id"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)  # individuals only
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(15), nullable=False, default=CustomerStatus.PROSPECT.value, index=True)
    created_at: Mapped[date] = mapped_column(Date, nullable=False)
    onboarded_at: Mapped[date | None] = mapped_column(Date)  # set when approved

    __table_args__ = (
        values_check("status", CustomerStatus, "ck_customer_status"),
        CheckConstraint(
            "onboarded_at IS NULL OR onboarded_at >= created_at",
            name="ck_customer_dates",
        ),
    )

    customer_type = relationship("CustomerType", back_populates="customers")
    business_profile = relationship("BusinessProfile", back_populates="customer", uselist=False)
    risk_ratings = relationship("RiskRating", back_populates="customer")
    documents = relationship("Document", back_populates="customer")
    review_cases = relationship("ReviewCase", back_populates="customer")
    alerts = relationship("Alert", back_populates="customer")
    ownership_links = relationship("OwnershipLink", back_populates="customer")


class BusinessProfile(Base):
    """1:1 optional extension of Customer; exists only for business customers."""

    __tablename__ = "business_profile"

    # Primary key AND foreign key at once: that is what makes the relationship 1:1.
    customer_id: Mapped[str] = mapped_column(String(10), ForeignKey("customer.customer_id"), primary_key=True)
    registration_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    incorporation_date: Mapped[date] = mapped_column(Date, nullable=False)
    country_of_incorporation: Mapped[str] = mapped_column(String(2), nullable=False)

    customer = relationship("Customer", back_populates="business_profile")


class RiskRating(Base):
    """Risk history. The CURRENT rating is the row where effective_to IS NULL."""

    __tablename__ = "risk_rating"

    rating_id: Mapped[str] = mapped_column(String(30), primary_key=True)  # RSK-CUS-000001-001
    customer_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("customer.customer_id"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        values_check("level", RiskLevel, "ck_risk_rating_level"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_risk_rating_score"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_risk_rating_dates",
        ),
        UniqueConstraint("customer_id", "effective_from", name="uq_risk_rating_customer_start"),
    )

    customer = relationship("Customer", back_populates="risk_ratings")
