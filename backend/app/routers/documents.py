"""GET /api/documents (paginated, filtered) and GET /api/documents/{id}."""
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.enums import DocumentStatus
from app.routers.common import Order, PageParams, make_page, text_match
from app.schemas.common import Page
from app.schemas.documents import DocumentDetail, DocumentListItem
from app.services.customer_view import document_columns, document_view, requirement_ids_for

router = APIRouter(prefix="/documents", tags=["documents"])

DocState = Literal["VALID", "PENDING", "EXPIRED", "REJECTED", "IGNORED"]
DocSort = Literal["document_id", "submitted_at", "expiry_date", "issue_date"]


def _state_clause(state: str, as_of):
    """SQL twin of services.completeness.document_state (a test proves they agree)."""
    from app.models import Document as D
    if state == "VALID":
        return and_(D.status == "VERIFIED", or_(D.expiry_date.is_(None), D.expiry_date >= as_of))
    if state == "EXPIRED":
        return or_(D.status == "EXPIRED", and_(D.status == "VERIFIED", D.expiry_date.is_not(None), D.expiry_date < as_of))
    return {"PENDING": D.status == "SUBMITTED", "REJECTED": D.status == "REJECTED",
            "IGNORED": D.status == "SUPERSEDED"}[state]


@router.get("", response_model=Page[DocumentListItem])
def list_documents(
    params: PageParams = Depends(),
    status: DocumentStatus | None = None,
    state: DocState | None = Query(None, description="calculated state as of the system date"),
    customer_id: str | None = Query(None, max_length=10),
    requirement_id: str | None = Query(None, max_length=20),
    file_hash: str | None = Query(None, min_length=64, max_length=64),
    expiring_within_days: int | None = Query(None, ge=0, le=3650, description="verified, expires in N days"),
    expiry_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    expiry_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    q: str | None = Query(None, min_length=1, max_length=100),
    sort: DocSort = "document_id",
    order: Order = "asc",
    db: Session = Depends(get_db),
):
    from datetime import date

    from app.models import Customer as C, Document as D, document_requirement_link as link

    as_of = settings.as_of_date
    filters = []
    if status:
        filters.append(D.status == status.value)
    if state:
        filters.append(_state_clause(state, as_of))
    if customer_id:
        filters.append(D.customer_id == customer_id)
    if requirement_id:
        filters.append(D.document_id.in_(select(link.c.document_id).where(link.c.requirement_id == requirement_id)))
    if file_hash:
        filters.append(D.file_hash == file_hash.lower())
    if expiring_within_days is not None:
        filters += [D.status == "VERIFIED", D.expiry_date >= as_of,
                    D.expiry_date <= as_of + timedelta(days=expiring_within_days)]
    try:
        if expiry_from:
            filters.append(D.expiry_date >= date.fromisoformat(expiry_from))
        if expiry_to:
            filters.append(D.expiry_date <= date.fromisoformat(expiry_to))
    except ValueError:
        raise HTTPException(status_code=422, detail="expiry_from / expiry_to must be real dates (YYYY-MM-DD)")
    if q:
        filters.append(text_match(D.document_id, q) | text_match(D.file_name, q) | text_match(C.full_name, q))

    sort_col = {"document_id": D.document_id, "submitted_at": D.submitted_at, "expiry_date": D.expiry_date,
                "issue_date": D.issue_date}[sort]
    ordering = [sort_col.asc() if order == "asc" else sort_col.desc(), D.document_id.asc()]
    base = select(*document_columns(), C.full_name.label("customer_name")).join(C, C.customer_id == D.customer_id)
    total = db.scalar(select(func.count()).select_from(D).join(C, C.customer_id == D.customer_id).where(*filters))
    rows = [dict(r) for r in db.execute(
        base.where(*filters).order_by(*ordering).limit(params.page_size).offset(params.offset)).mappings()]
    req = requirement_ids_for(db, [r["document_id"] for r in rows])
    items = [{**document_view(r, as_of, req.get(r["document_id"], [])), "customer_name": r["customer_name"]}
             for r in rows]
    return make_page(items, total, params)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str, db: Session = Depends(get_db)):
    from app.models import Alert, Customer, Document, Verification

    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    as_of = settings.as_of_date
    row = {c.name: getattr(doc, c.name) for c in Document.__table__.columns}
    req = requirement_ids_for(db, [document_id])
    same_hash = list(db.scalars(select(Document.document_id).where(
        Document.file_hash == doc.file_hash, Document.document_id != document_id).order_by(Document.document_id)))
    return {
        **document_view(row, as_of, req.get(document_id, [])),
        "customer_name": db.get(Customer, doc.customer_id).full_name,
        "verifications": list(db.scalars(select(Verification).where(Verification.document_id == document_id)
                                         .order_by(Verification.verification_id))),
        "alerts": list(db.scalars(select(Alert).where(Alert.document_id == document_id)
                                  .order_by(Alert.alert_id))),
        "duplicate_of": same_hash,
    }
