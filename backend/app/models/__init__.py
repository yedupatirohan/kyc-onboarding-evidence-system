"""Importing this package registers every table on Base.metadata."""
from app.models.compliance import Alert, AuditEvent, BeneficialOwner, OwnershipLink, ReviewCase
from app.models.customer import BusinessProfile, Customer, RiskRating
from app.models.evidence import Document, Verification, document_requirement_link
from app.models.reference import CustomerType, KYCRequirement, customer_type_requirement

__all__ = [
    "Alert",
    "AuditEvent",
    "BeneficialOwner",
    "BusinessProfile",
    "Customer",
    "CustomerType",
    "Document",
    "KYCRequirement",
    "OwnershipLink",
    "ReviewCase",
    "RiskRating",
    "Verification",
    "customer_type_requirement",
    "document_requirement_link",
]
