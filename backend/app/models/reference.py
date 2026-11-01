"""Reference (master) data: customer types and KYC requirements."""
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Column, Date, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import RiskLevel, values_check

# Bridge table (N:M): which requirements apply to which customer types.
customer_type_requirement = Table(
    "customer_type_requirement",
    Base.metadata,
    Column("customer_type_id", String(30), ForeignKey("customer_type.customer_type_id"), primary_key=True),
    Column("requirement_id", String(20), ForeignKey("kyc_requirement.requirement_id"), primary_key=True),
)


class CustomerType(Base):
    __tablename__ = "customer_type"

    customer_type_id: Mapped[str] = mapped_column(String(30), primary_key=True)  # e.g. COMPANY
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_business: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    customers = relationship("Customer", back_populates="customer_type")
    requirements = relationship(
        "KYCRequirement", secondary=customer_type_requirement, back_populates="customer_types"
    )


class KYCRequirement(Base):
    __tablename__ = "kyc_requirement"

    requirement_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # KYC-2026-000001
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Requirement applies to customers whose risk is at or above this level.
    min_risk_level: Mapped[str] = mapped_column(String(10), nullable=False, default=RiskLevel.LOW.value)
    # How long a document for this requirement stays valid (None = no expiry rule).
    validity_months: Mapped[int | None] = mapped_column(Integer)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        values_check("min_risk_level", RiskLevel, "ck_kyc_requirement_min_risk"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_kyc_requirement_dates",
        ),
        CheckConstraint(
            "validity_months IS NULL OR validity_months > 0",
            name="ck_kyc_requirement_validity",
        ),
    )

    customer_types = relationship(
        "CustomerType", secondary=customer_type_requirement, back_populates="requirements"
    )
    documents = relationship(
        "Document", secondary="document_requirement_link", back_populates="requirements"
    )
