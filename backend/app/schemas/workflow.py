"""Response models for reviews, alerts, exceptions and the audit trail."""
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.customers import AlertOut, ReviewOut


class ReviewListItem(ReviewOut):
    customer_name: str
    risk_level: str | None
    days_overdue: int | None      # > 0 only when due date has passed and the review is not CLOSED


class ReviewDetail(ReviewListItem):
    customer_status: str
    onboarded_at: date | None


class AlertListItem(AlertOut):
    customer_name: str


class AlertDetail(AlertListItem):
    customer_status: str
    document_status: str | None
    document_expiry_date: date | None
    is_exception: bool            # one of the five mandatory anomaly types
    rule: str | None
    expected_decision: str | None


class ExceptionItem(AlertListItem):
    rule: str
    expected_decision: str


class ExceptionSummaryItem(BaseModel):
    issue_type: str
    severity: str
    rule: str
    expected_decision: str
    total: int
    open: int
    acknowledged: int
    resolved: int


class AuditEventOut(BaseModel):
    event_id: str
    entity_type: str
    entity_id: str
    action: str
    old_value: Any | None         # parsed JSON when possible, else the raw text
    new_value: Any | None
    actor: str
    occurred_at: datetime
