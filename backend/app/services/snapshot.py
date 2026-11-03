"""One read path: load everything the rules need from the database into plain Python data."""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select

from app.config import settings
from app.services.requirements import RequirementSpec, load_requirement_specs


@dataclass
class Snapshot:
    as_of: date
    customers: list[dict]
    current_risk: dict[str, str]
    specs: list[RequirementSpec]
    documents: list[dict]                 # each has requirement_ids (tuple)
    reviews: list[dict]
    owner_links: list[dict]
    alerts: list[dict]
    docs_by_customer: dict[str, list[dict]] = field(default_factory=dict)


def _rows(session, statement) -> list[dict]:
    return [dict(r) for r in session.execute(statement).mappings()]


def load_snapshot(session, as_of: date | None = None) -> Snapshot:
    from app.models import (Alert, Customer, Document, OwnershipLink, ReviewCase, RiskRating,
                            document_requirement_link)

    as_of = settings.as_of_date if as_of is None else as_of
    customers = _rows(session, select(Customer).order_by(Customer.customer_id).with_only_columns(
        Customer.customer_id, Customer.customer_type_id, Customer.full_name, Customer.status,
        Customer.created_at, Customer.onboarded_at, Customer.country_code))
    current_risk = dict(session.execute(
        select(RiskRating.customer_id, RiskRating.level).where(RiskRating.effective_to.is_(None))).all())

    req_ids: dict[str, list[str]] = defaultdict(list)
    for document_id, requirement_id in session.execute(
            select(document_requirement_link.c.document_id, document_requirement_link.c.requirement_id)
            .order_by(document_requirement_link.c.document_id, document_requirement_link.c.requirement_id)):
        req_ids[document_id].append(requirement_id)
    documents = _rows(session, select(
        Document.document_id, Document.customer_id, Document.file_hash, Document.issue_date,
        Document.expiry_date, Document.status, Document.submitted_at).order_by(Document.document_id))
    docs_by_customer: dict[str, list[dict]] = defaultdict(list)
    for d in documents:
        d["requirement_ids"] = tuple(req_ids[d["document_id"]])
        docs_by_customer[d["customer_id"]].append(d)

    return Snapshot(
        as_of=as_of, customers=customers, current_risk=current_risk,
        specs=load_requirement_specs(session), documents=documents,
        reviews=_rows(session, select(
            ReviewCase.review_id, ReviewCase.customer_id, ReviewCase.due_date, ReviewCase.status,
            ReviewCase.opened_at, ReviewCase.closed_at, ReviewCase.resolution, ReviewCase.closed_by
        ).order_by(ReviewCase.review_id)),
        owner_links=_rows(session, select(
            OwnershipLink.link_id, OwnershipLink.customer_id, OwnershipLink.owner_id,
            OwnershipLink.ownership_pct, OwnershipLink.effective_from, OwnershipLink.effective_to
        ).order_by(OwnershipLink.link_id)),
        alerts=_rows(session, select(
            Alert.alert_id, Alert.customer_id, Alert.document_id, Alert.alert_type, Alert.severity,
            Alert.status, Alert.lead_days, Alert.created_at).order_by(Alert.alert_id)),
        docs_by_customer=dict(docs_by_customer),
    )
