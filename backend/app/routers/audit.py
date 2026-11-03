"""GET /api/audit-events: the append-only history of important changes."""
import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.common import Order, PageParams, day_start, make_page, next_day_start, text_match
from app.schemas.common import Page
from app.schemas.workflow import AuditEventOut

router = APIRouter(prefix="/audit-events", tags=["audit"])

AuditSort = Literal["occurred_at", "event_id"]


def _parse(text):
    if text is None:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def _out(e) -> dict:
    return {"event_id": e.event_id, "entity_type": e.entity_type, "entity_id": e.entity_id, "action": e.action,
            "old_value": _parse(e.old_value), "new_value": _parse(e.new_value), "actor": e.actor,
            "occurred_at": e.occurred_at}


@router.get("/facets")
def facets(db: Session = Depends(get_db)) -> dict:
    """Distinct values for the UI filter dropdowns."""
    from app.models import AuditEvent as E
    return {name: [v for (v,) in db.execute(select(col).distinct().order_by(col))]
            for name, col in (("entity_types", E.entity_type), ("actions", E.action), ("actors", E.actor))}


@router.get("", response_model=Page[AuditEventOut])
def list_audit_events(
    params: PageParams = Depends(),
    entity_type: str | None = Query(None, max_length=30),
    entity_id: str | None = Query(None, max_length=40, description="exact id, e.g. CUS-000001"),
    action: str | None = Query(None, max_length=30),
    actor: str | None = Query(None, max_length=100),
    occurred_from: date | None = None,
    occurred_to: date | None = Query(None, description="inclusive day"),
    q: str | None = Query(None, min_length=1, max_length=100, description="entity id contains"),
    sort: AuditSort = "occurred_at",
    order: Order = "desc",
    db: Session = Depends(get_db),
):
    from app.models import AuditEvent as E

    filters = []
    if entity_type:
        filters.append(E.entity_type == entity_type)
    if entity_id:
        filters.append(E.entity_id == entity_id)
    if action:
        filters.append(E.action == action)
    if actor:
        filters.append(E.actor == actor)
    if occurred_from:
        filters.append(E.occurred_at >= day_start(occurred_from))
    if occurred_to:
        filters.append(E.occurred_at < next_day_start(occurred_to))
    if occurred_from and occurred_to and occurred_from > occurred_to:
        raise HTTPException(status_code=422, detail="occurred_from must not be after occurred_to")
    if q:
        filters.append(text_match(E.entity_id, q))

    col = E.occurred_at if sort == "occurred_at" else E.event_id
    ordering = [col.asc() if order == "asc" else col.desc(), E.event_id.asc()]
    total = db.scalar(select(func.count()).select_from(E).where(*filters))
    rows = db.scalars(select(E).where(*filters).order_by(*ordering).limit(params.page_size).offset(params.offset))
    return make_page([_out(e) for e in rows], total, params)


@router.get("/{event_id}", response_model=AuditEventOut)
def get_audit_event(event_id: str, db: Session = Depends(get_db)):
    from app.models import AuditEvent as E
    event = db.get(E, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Audit event {event_id} not found")
    return _out(event)
