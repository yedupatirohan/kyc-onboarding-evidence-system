"""Exceptions = alerts of the five mandatory anomaly types (kept in sync by run_exception_scan)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import AlertSeverity, AlertStatus, AlertType
from app.routers.alerts import alert_columns, alert_from
from app.routers.common import PageParams, make_page, text_match
from app.schemas.common import Page
from app.schemas.workflow import ExceptionItem, ExceptionSummaryItem
from app.services.anomaly_detection import EXPECTED_DECISION, ISSUE_TYPES, RULES, SEVERITY

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("/summary", response_model=list[ExceptionSummaryItem])
def exception_summary(db: Session = Depends(get_db)):
    from app.models import Alert as A

    counts = {(t, s): n for t, s, n in db.execute(
        select(A.alert_type, A.status, func.count()).where(A.alert_type.in_(ISSUE_TYPES))
        .group_by(A.alert_type, A.status))}
    out = []
    for issue in ISSUE_TYPES:
        by = {s: counts.get((issue, s), 0) for s in ("OPEN", "ACKNOWLEDGED", "RESOLVED")}
        out.append({"issue_type": issue, "severity": SEVERITY[issue], "rule": RULES[issue],
                    "expected_decision": EXPECTED_DECISION[issue], "total": sum(by.values()),
                    "open": by["OPEN"], "acknowledged": by["ACKNOWLEDGED"], "resolved": by["RESOLVED"]})
    return out


@router.get("", response_model=Page[ExceptionItem])
def list_exceptions(
    params: PageParams = Depends(),
    issue_type: AlertType | None = None,
    severity: AlertSeverity | None = None,
    status: AlertStatus | None = None,
    customer_id: str | None = Query(None, max_length=10),
    q: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    from app.models import Alert as A, Customer as C

    if issue_type and issue_type.value not in ISSUE_TYPES:
        raise HTTPException(status_code=422, detail=f"{issue_type.value} is not an exception type; "
                                                    f"use one of {', '.join(ISSUE_TYPES)}")
    filters = [A.alert_type.in_(ISSUE_TYPES)]
    if issue_type:
        filters.append(A.alert_type == issue_type.value)
    if severity:
        filters.append(A.severity == severity.value)
    if status:
        filters.append(A.status == status.value)
    if customer_id:
        filters.append(A.customer_id == customer_id)
    if q:
        filters.append(text_match(A.alert_id, q) | text_match(A.message, q) | text_match(C.full_name, q))

    total = db.scalar(alert_from(select(func.count())).where(*filters))
    rows = db.execute(alert_from(select(*alert_columns())).where(*filters)
                      .order_by(A.alert_type.asc(), A.alert_id.asc())
                      .limit(params.page_size).offset(params.offset)).mappings().all()
    items = [{**r, "rule": RULES[r["alert_type"]], "expected_decision": EXPECTED_DECISION[r["alert_type"]]}
             for r in rows]
    return make_page(items, total, params)
