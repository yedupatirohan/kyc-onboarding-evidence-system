"""Response models for customers, businesses and the records hanging off them."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MissingItem(BaseModel):
    requirement_id: str
    name: str
    state: str            # MISSING / PENDING / EXPIRED / REJECTED
    reason: str


class CompletenessOut(BaseModel):
    required: int
    satisfied: int
    percent: float
    label: str            # COMPLETE / INCOMPLETE / PENDING_VERIFICATION
    missing: list[MissingItem] = []


class CustomerListItem(BaseModel):
    customer_id: str
    full_name: str
    customer_type_id: str
    country_code: str
    status: str
    risk_level: str | None
    risk_score: int | None
    created_at: date
    onboarded_at: date | None
    completeness_percent: float
    completeness_label: str
    missing_count: int


class RiskHistoryItem(ORMModel):
    rating_id: str
    level: str
    score: int
    effective_from: date
    effective_to: date | None
    reason: str | None


class DocumentOut(BaseModel):
    document_id: str
    customer_id: str
    file_name: str
    file_hash: str
    file_size_bytes: int
    issue_date: date
    expiry_date: date | None
    status: str                   # stored status
    effective_state: str          # VALID / PENDING / EXPIRED / REJECTED / IGNORED (calculated)
    days_to_expiry: int | None    # negative = already expired
    submitted_at: date
    requirement_ids: list[str]


class ReviewOut(ORMModel):
    review_id: str
    customer_id: str
    due_date: date
    status: str
    opened_at: date | None
    closed_at: date | None
    resolution: str | None
    closed_by: str | None


class AlertOut(ORMModel):
    alert_id: str
    customer_id: str
    document_id: str | None
    alert_type: str
    severity: str
    status: str
    lead_days: int | None
    message: str
    created_at: date
    resolved_at: date | None


class OwnershipOut(BaseModel):
    link_id: str
    owner_id: str
    owner_name: str
    ownership_pct: float
    effective_from: date
    effective_to: date | None
    active: bool


class BusinessProfileOut(ORMModel):
    registration_number: str
    incorporation_date: date
    country_of_incorporation: str


class CustomerDetail(BaseModel):
    customer_id: str
    full_name: str
    customer_type_id: str
    customer_type_name: str
    country_code: str
    email: str | None
    date_of_birth: date | None
    status: str
    created_at: date
    onboarded_at: date | None
    risk_level: str | None
    risk_score: int | None
    next_review_due: date | None
    business_profile: BusinessProfileOut | None
    risk_history: list[RiskHistoryItem]
    completeness: CompletenessOut
    documents: list[DocumentOut]
    reviews: list[ReviewOut]
    alerts: list[AlertOut]
    ownership: list[OwnershipOut]
    ownership_active_total: float | None


class BusinessListItem(BaseModel):
    customer_id: str
    full_name: str
    customer_type_id: str
    status: str
    risk_level: str | None
    registration_number: str
    incorporation_date: date
    country_of_incorporation: str
    active_owner_count: int
    active_ownership_pct: float
    ownership_exceeds_100: bool


class VerificationOut(ORMModel):
    verification_id: str
    result: str
    verified_by: str | None
    verified_at: datetime | None
    notes: str | None
