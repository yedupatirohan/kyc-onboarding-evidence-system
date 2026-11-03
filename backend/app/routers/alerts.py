"""GET /api/alerts and /api/alerts/{id}."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import AlertSeverity, AlertStatus, AlertType
from app.routers.common import Order, PageParams, make_page, text_match
from app.schemas.common import Page
from app.schemas.workflow import AlertDetail, AlertListItem
from app.services.anomaly_detection import EXPECTED_DECISION, ISSUE_TYPES, RULES

router = APIRouter(prefix="/alerts", tags=["alerts"])

AlertSort = Literal["created_at", "severity", "alert_id"]


def alert_columns():
    from app.models import Alert as A, Customer as C
    return (A.alert_id, A.customer_id, A.document_id, A.alert_type, A.severity, A.status, A.lead_days,
            A.message, A.created_at, A.resolved_at, C.full_name.label("customer_name"))


def alert_from(stmt):
    from app.models import Alert as A, Customer as C
    return stmt.select_from(A).join(C, C.customer_id == A.customer_id)


def severity_rank():
    from app.models import Alert as A
    return case((A.severity == "CRITICAL", 4), (A.severity == "HIGH", 3), (A.severity == "MEDIUM", 2),
                (A.severity == "LOW", 1), else_=0)


@router.get("", response_model=Page[AlertListItem])
def list_alerts(
    params: PageParams = Depends(),
    alert_type: AlertType | None = None,
    severity: AlertSeverity | None = None,
    status: AlertStatus | None = None,
    customer_id: str | None = Query(None, max_length=10),
    document_id: str | None = Query(None, max_length=20),
    lead_days: int | None = Query(None, ge=0, le=3650, description="expiry warnings: 90 / 60 / 30"),
    created_from: date | None = None,
    created_to: date | None = None,
    q: str | None = Query(None, min_length=1, max_length=100, description="alert id, message or customer name"),
    sort: AlertSort = "created_at",
    order: Order = "desc",
    db: Session = Depends(get_db),
):
    from app.models import Alert as A, Customer as C

    filters = []
    if alert_type:
        filters.append(A.alert_type == alert_type.value)
    if severity:
        filters.append(A.severity == severity.value)
    if status:
        filters.append(A.status == status.value)
    if customer_id:
        filters.append(A.customer_id == customer_id)
    if document_id:
        filters.append(A.document_id == document_id)
    if lead_days is not None:
        filters.append(A.lead_days == lead_days)
    if created_from:
        filters.append(A.created_at >= created_from)
    if created_to:
        filters.append(A.created_at <= created_to)
    if created_from and created_to and created_from > created_to:
        raise HTTPException(status_code=422, detail="created_from must not be after created_to")
    if q:
        filters.append(text_match(A.alert_id, q) | text_match(A.message, q) | text_match(C.full_name, q))

    col = {"created_at": A.created_at, "severity": severity_rank(), "alert_id": A.alert_id}[sort]
    ordering = [col.asc() if order == "asc" else col.desc(), A.alert_id.asc()]
    total = db.scalar(alert_from(select(func.count())).where(*filters))
    rows = db.execute(alert_from(select(*alert_columns())).where(*filters).order_by(*ordering)
                      .limit(params.page_size).offset(params.offset)).mappings().all()
    return make_page([dict(r) for r in rows], total, params)


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    from app.models import Alert as A, Customer as C, Document as D

    row = db.execute(alert_from(select(*alert_columns(), C.status.label("customer_status")))
                     .where(A.alert_id == alert_id)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    out = dict(row)
    doc = db.get(D, out["document_id"]) if out["document_id"] else None
    out["document_status"] = doc.status if doc else None
    out["document_expiry_date"] = doc.expiry_date if doc else None
    out["is_exception"] = out["alert_type"] in ISSUE_TYPES
    out["rule"] = RULES.get(out["alert_type"])
    out["expected_decision"] = EXPECTED_DECISION.get(out["alert_type"])
    return out
