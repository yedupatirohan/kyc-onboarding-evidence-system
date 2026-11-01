"""Evidence: documents, the verification history and the document-requirement bridge."""
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import DocumentStatus, VerificationResult, values_check

# Bridge table (N:M): one document may satisfy several requirements.
document_requirement_link = Table(
    "document_requirement_link",
    Base.metadata,
    Column("document_id", String(20), ForeignKey("document.document_id"), primary_key=True),
    Column("requirement_id", String(20), ForeignKey("kyc_requirement.requirement_id"), primary_key=True),
)


class Document(Base):
    __tablename__ = "document"

    document_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # DOC-CUS-000001-001
    customer_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("customer.customer_id"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 hex digest. Indexed (not unique): duplicates across customers are anomaly #5.
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    # Cached current state. The Verification table holds the real history.
    status: Mapped[str] = mapped_column(String(15), nullable=False, default=DocumentStatus.SUBMITTED.value, index=True)
    submitted_at: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        values_check("status", DocumentStatus, "ck_document_status"),
        CheckConstraint(
            "expiry_date IS NULL OR expiry_date >= issue_date",
            name="ck_document_dates",
        ),
        CheckConstraint("file_size_bytes > 0", name="ck_document_size"),
    )

    customer = relationship("Customer", back_populates="documents")
    verifications = relationship("Verification", back_populates="document")
    alerts = relationship("Alert", back_populates="document")
    requirements = relationship(
        "KYCRequirement", secondary=document_requirement_link, back_populates="documents"
    )


class Verification(Base):
    """One row per verification EVENT. Never updated, a new row is added instead."""

    __tablename__ = "verification"

    verification_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("document.document_id"), nullable=False, index=True
    )
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    verified_by: Mapped[str | None] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)  # NULL while PENDING
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (values_check("result", VerificationResult, "ck_verification_result"),)

    document = relationship("Document", back_populates="verifications")
