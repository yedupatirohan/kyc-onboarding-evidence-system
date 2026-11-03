"""GET /api/reviews and /api/reviews/{id}."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.enums import ReviewStatus, RiskLevel
from app.routers.common import Order, PageParams, make_page, text_match
from app.schemas.common import Page
from app.schemas.workflow import ReviewDetail, ReviewListItem
from app.services.review_schedule import is_overdue

router = APIRouter(prefix="/reviews", tags=["reviews"])

ReviewSort = Literal["due_date", "review_id", "closed_at", "opened_at"]


def _item(row, as_of: date) -> dict:
    d = dict(row._mapping)
    d["days_overdue"] = (as_of - d["due_date"]).days if is_overdue(d["due_date"], d["status"], as_of) else None
    return d


def _columns():
    from app.models import Customer as C, ReviewCase as V, RiskRating as R
    return (V.review_id, V.customer_id, V.due_date, V.status, V.opened_at, V.closed_at, V.resolution,
            V.closed_by, C.full_name.label("customer_name"), R.level.label("risk_level"))


def _from(stmt):
    from app.models import Customer as C, ReviewCase as V, RiskRating as R
    current = and_(R.customer_id == C.customer_id, R.effective_to.is_(None))
    return stmt.select_from(V).join(C, C.customer_id == V.customer_id).outerjoin(R, current)


@router.get("", response_model=Page[ReviewListItem])
def list_reviews(
    params: PageParams = Depends(),
    status: ReviewStatus | None = None,
    customer_id: str | None = Query(None, max_length=10),
    risk_level: RiskLevel | None = None,
    overdue: bool | None = Query(None, description="calculated: due date passed and not CLOSED"),
    closed_without_resolution: bool | None = Query(None, description="CLOSED with an empty resolution"),
    due_from: date | None = None,
    due_to: date | None = None,
    q: str | None = Query(None, min_length=1, max_length=100),
    sort: ReviewSort = "due_date",
    order: Order = "asc",
    db: Session = Depends(get_db),
):
    from app.models import Customer as C, ReviewCase as V, RiskRating as R

    as_of = settings.as_of_date
    filters = []
    if status:
        filters.append(V.status == status.value)
    if customer_id:
        filters.append(V.customer_id == customer_id)
    if risk_level:
        filters.append(R.level == risk_level.value)
    if overdue is not None:
        cond = and_(V.due_date < as_of, V.status != "CLOSED")
        filters.append(cond if overdue else ~cond)
    if closed_without_resolution is not None:
        cond = and_(V.status == "CLOSED", func.trim(func.coalesce(V.resolution, "")) == "")
        filters.append(cond if closed_without_resolution else ~cond)
    if due_from:
        filters.append(V.due_date >= due_from)
    if due_to:
        filters.append(V.due_date <= due_to)
    if due_from and due_to and due_from > due_to:
        raise HTTPException(status_code=422, detail="due_from must not be after due_to")
    if q:
        filters.append(text_match(V.review_id, q) | text_match(V.customer_id, q) | text_match(C.full_name, q))

    col = {"due_date": V.due_date, "review_id": V.review_id, "closed_at": V.closed_at, "opened_at": V.opened_at}[sort]
    ordering = [col.asc() if order == "asc" else col.desc(), V.review_id.asc()]
    total = db.scalar(_from(select(func.count())).where(*filters))
    rows = db.execute(_from(select(*_columns())).where(*filters).order_by(*ordering)
                      .limit(params.page_size).offset(params.offset)).all()
    return make_page([_item(r, as_of) for r in rows], total, params)


@router.get("/{review_id}", response_model=ReviewDetail)
def get_review(review_id: str, db: Session = Depends(get_db)):
    from app.models import Customer as C, ReviewCase as V

    row = db.execute(_from(select(*_columns(), C.status.label("customer_status"), C.onboarded_at))
                     .where(V.review_id == review_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Review {review_id} not found")
    return _item(row, settings.as_of_date)
