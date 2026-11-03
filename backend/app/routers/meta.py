"""Health and reference data (feeds the UI dropdowns)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.enums import (AlertSeverity, AlertStatus, AlertType, CustomerStatus, DocumentStatus, ReviewStatus,
                       RiskLevel)
from app.services.requirements import load_requirement_specs

router = APIRouter(tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    from app.models import Alert, Customer, Document, ReviewCase
    info = {"status": "ok", "as_of_date": settings.as_of_date.isoformat(), "seed": settings.seed}
    try:
        info["counts"] = {name: db.scalar(select(func.count()).select_from(model))
                          for name, model in (("customers", Customer), ("documents", Document),
                                              ("reviews", ReviewCase), ("alerts", Alert))}
        if not info["counts"]["customers"]:
            info["status"] = "empty"        # tables exist but the generator has not been run
    except Exception:                       # tables missing entirely
        info["status"] = "no_database"
    return info


@router.get("/meta/enums")
def enums() -> dict:
    return {name: [e.value for e in enum] for name, enum in (
        ("customer_status", CustomerStatus), ("risk_level", RiskLevel), ("document_status", DocumentStatus),
        ("review_status", ReviewStatus), ("alert_type", AlertType), ("alert_severity", AlertSeverity),
        ("alert_status", AlertStatus))} | {
        "document_state": ["VALID", "PENDING", "EXPIRED", "REJECTED", "IGNORED"],
        "completeness_label": ["COMPLETE", "INCOMPLETE", "PENDING_VERIFICATION"],
    }


@router.get("/meta/customer-types")
def customer_types(db: Session = Depends(get_db)) -> list[dict]:
    from app.models import CustomerType
    return [{"customer_type_id": t.customer_type_id, "name": t.name, "is_business": t.is_business}
            for t in db.scalars(select(CustomerType).order_by(CustomerType.customer_type_id))]


@router.get("/meta/requirements")
def requirements(db: Session = Depends(get_db)) -> list[dict]:
    return [{
        "requirement_id": s.requirement_id, "name": s.name, "is_mandatory": s.is_mandatory,
        "min_risk_level": s.min_risk_level, "validity_months": s.validity_months,
        "effective_from": s.effective_from, "effective_to": s.effective_to,
        "customer_type_ids": sorted(s.customer_type_ids),
    } for s in load_requirement_specs(db)]
