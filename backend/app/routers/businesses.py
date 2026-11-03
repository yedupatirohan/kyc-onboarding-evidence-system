"""GET /api/businesses: business customers with their (active) beneficial ownership total."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.enums import CustomerStatus, RiskLevel
from app.routers.common import Order, PageParams, make_page, text_match
from app.schemas.common import Page
from app.schemas.customers import BusinessListItem
from app.services.customer_view import ownership_summary

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("", response_model=Page[BusinessListItem])
def list_businesses(
    params: PageParams = Depends(),
    status: CustomerStatus | None = None,
    risk_level: RiskLevel | None = None,
    country_of_incorporation: str | None = Query(None, min_length=2, max_length=2),
    ownership_over_100: bool | None = Query(None, description="true = only businesses whose active ownership exceeds 100%"),
    q: str | None = Query(None, min_length=1, max_length=100, description="name, id or registration number"),
    order: Order = "asc",
    db: Session = Depends(get_db),
):
    from app.models import BusinessProfile as B, Customer as C, RiskRating as R

    as_of = settings.as_of_date
    current = and_(R.customer_id == C.customer_id, R.effective_to.is_(None))
    filters = []
    if status:
        filters.append(C.status == status.value)
    if risk_level:
        filters.append(R.level == risk_level.value)
    if country_of_incorporation:
        filters.append(B.country_of_incorporation == country_of_incorporation.upper())
    if q:
        filters.append(text_match(C.full_name, q) | text_match(C.customer_id, q) | text_match(B.registration_number, q))
    if ownership_over_100 is not None:
        # Same Decimal arithmetic as the detector (never SQL float sums, which can round 100.00 up).
        over = sorted(cid for cid, s in ownership_summary(db, None, as_of).items() if s["total"] > 100)
        filters.append(C.customer_id.in_(over) if ownership_over_100 else C.customer_id.not_in(over))

    ordering = [C.customer_id.asc() if order == "asc" else C.customer_id.desc()]
    total = db.scalar(select(func.count()).select_from(C).join(B, B.customer_id == C.customer_id)
                      .outerjoin(R, current).where(*filters))
    rows = db.execute(
        select(C.customer_id, C.full_name, C.customer_type_id, C.status, R.level.label("risk_level"),
               B.registration_number, B.incorporation_date, B.country_of_incorporation)
        .select_from(C).join(B, B.customer_id == C.customer_id).outerjoin(R, current)
        .where(*filters).order_by(*ordering).limit(params.page_size).offset(params.offset)).all()
    own = ownership_summary(db, [r.customer_id for r in rows], as_of)
    items = []
    for r in rows:
        s = own.get(r.customer_id, {"total": 0, "count": 0})
        items.append({**r._mapping, "active_owner_count": s["count"], "active_ownership_pct": float(s["total"]),
                      "ownership_exceeds_100": s["total"] > 100})
    return make_page(items, total, params)
