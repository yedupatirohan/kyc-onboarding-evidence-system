"""GET /api/customers (paginated, filtered, sorted) and GET /api/customers/{id}."""
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.enums import CustomerStatus, RiskLevel
from app.routers.common import Order, PageParams, make_page, text_match
from app.schemas.common import Page
from app.schemas.customers import CustomerDetail, CustomerListItem
from app.services.customer_view import (completeness_for, document_columns, document_view, ownership_summary,
                                        requirement_ids_for)
from app.services.review_schedule import current_cycle_due_date

router = APIRouter(prefix="/customers", tags=["customers"])

CompletenessLabel = Literal["COMPLETE", "INCOMPLETE", "PENDING_VERIFICATION"]
CustomerSort = Literal["customer_id", "full_name", "created_at", "onboarded_at", "risk_score"]


@router.get("", response_model=Page[CustomerListItem])
def list_customers(
    params: PageParams = Depends(),
    status: CustomerStatus | None = None,
    customer_type_id: str | None = Query(None, max_length=30),
    country_code: str | None = Query(None, min_length=2, max_length=2),
    risk_level: RiskLevel | None = None,
    completeness: CompletenessLabel | None = Query(None, description="calculated, not stored"),
    q: str | None = Query(None, min_length=1, max_length=100, description="name or customer id contains"),
    sort: CustomerSort = "customer_id",
    order: Order = "asc",
    db: Session = Depends(get_db),
):
    from app.models import Customer as C, RiskRating as R

    current = and_(R.customer_id == C.customer_id, R.effective_to.is_(None))
    filters = []
    if status:
        filters.append(C.status == status.value)
    if customer_type_id:
        filters.append(C.customer_type_id == customer_type_id)
    if country_code:
        filters.append(C.country_code == country_code.upper())
    if risk_level:
        filters.append(R.level == risk_level.value)
    if q:
        filters.append(text_match(C.full_name, q) | text_match(C.customer_id, q))

    sort_col = {"customer_id": C.customer_id, "full_name": func.lower(C.full_name), "created_at": C.created_at,
                "onboarded_at": C.onboarded_at, "risk_score": R.score}[sort]
    ordering = [sort_col.asc() if order == "asc" else sort_col.desc(), C.customer_id.asc()]
    columns = (C.customer_id, C.customer_type_id, C.full_name, C.country_code, C.status, C.created_at,
               C.onboarded_at, R.level.label("risk_level"), R.score.label("risk_score"))
    rows_stmt = select(*columns).select_from(C).outerjoin(R, current).where(*filters).order_by(*ordering)
    as_of = settings.as_of_date

    def build(rows) -> list[dict]:
        results = completeness_for(db, [(r.customer_id, r.customer_type_id, r.risk_level) for r in rows], as_of)
        out = []
        for r in rows:
            c = results[r.customer_id]
            out.append({**r._mapping, "completeness_percent": c.percent, "completeness_label": c.label,
                        "missing_count": len(c.missing)})
        return out

    if completeness:
        # Completeness is calculated, so it cannot be a SQL filter: calculate for every match, then page.
        items = [i for i in build(db.execute(rows_stmt).all()) if i["completeness_label"] == completeness]
        start = params.offset
        return make_page(items[start:start + params.page_size], len(items), params)

    total = db.scalar(select(func.count()).select_from(C).outerjoin(R, current).where(*filters))
    rows = db.execute(rows_stmt.limit(params.page_size).offset(params.offset)).all()
    return make_page(build(rows), total, params)


@router.get("/{customer_id}", response_model=CustomerDetail)
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    from app.models import (Alert, BeneficialOwner, BusinessProfile, Customer, CustomerType, Document,
                            OwnershipLink, ReviewCase, RiskRating)

    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    as_of = settings.as_of_date

    history = list(db.scalars(select(RiskRating).where(RiskRating.customer_id == customer_id)
                              .order_by(RiskRating.effective_from.desc())))
    current = next((r for r in history if r.effective_to is None), None)
    risk_level = current.level if current else None

    doc_rows = [dict(r) for r in db.execute(
        select(*document_columns()).where(Document.customer_id == customer_id).order_by(Document.document_id)
    ).mappings()]
    req = requirement_ids_for(db, [d["document_id"] for d in doc_rows])
    comp = completeness_for(db, [(customer_id, customer.customer_type_id, risk_level)], as_of)[customer_id]

    reviews = list(db.scalars(select(ReviewCase).where(ReviewCase.customer_id == customer_id)
                              .order_by(ReviewCase.due_date.desc())))
    alerts = list(db.scalars(select(Alert).where(Alert.customer_id == customer_id)
                             .order_by(Alert.created_at.desc(), Alert.alert_id.desc())))

    owners = db.execute(
        select(OwnershipLink, BeneficialOwner.full_name).join(BeneficialOwner, BeneficialOwner.owner_id == OwnershipLink.owner_id)
        .where(OwnershipLink.customer_id == customer_id).order_by(OwnershipLink.link_id)).all()
    ownership = [{
        "link_id": l.link_id, "owner_id": l.owner_id, "owner_name": name, "ownership_pct": float(l.ownership_pct),
        "effective_from": l.effective_from, "effective_to": l.effective_to,
        "active": l.effective_from <= as_of and (l.effective_to is None or l.effective_to >= as_of),
    } for l, name in owners]
    own_total = ownership_summary(db, [customer_id], as_of).get(customer_id)

    next_due = None
    if customer.onboarded_at and risk_level:
        next_due = current_cycle_due_date(customer.onboarded_at, risk_level, as_of)

    return {
        "customer_id": customer.customer_id, "full_name": customer.full_name,
        "customer_type_id": customer.customer_type_id,
        "customer_type_name": db.get(CustomerType, customer.customer_type_id).name,
        "country_code": customer.country_code, "email": customer.email, "date_of_birth": customer.date_of_birth,
        "status": customer.status, "created_at": customer.created_at, "onboarded_at": customer.onboarded_at,
        "risk_level": risk_level, "risk_score": current.score if current else None, "next_review_due": next_due,
        "business_profile": db.get(BusinessProfile, customer_id),
        "risk_history": history,
        "completeness": asdict(comp),
        "documents": [document_view(d, as_of, req.get(d["document_id"], [])) for d in doc_rows],
        "reviews": reviews, "alerts": alerts, "ownership": ownership,
        "ownership_active_total": float(own_total["total"]) if own_total else (0.0 if ownership else None),
    }
