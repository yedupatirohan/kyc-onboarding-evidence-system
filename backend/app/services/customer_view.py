"""Read-side helpers for the API: they reuse the rule services, they never re-implement a rule."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.services.anomaly_detection import active_ownership_totals
from app.services.completeness import CompletenessResult, calculate_completeness, document_state
from app.services.requirements import load_requirement_specs

CHUNK = 500


def _chunks(values: list, size: int = CHUNK):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def requirement_ids_for(session, document_ids: list[str]) -> dict[str, list[str]]:
    from app.models import document_requirement_link as link

    out: dict[str, list[str]] = defaultdict(list)
    for chunk in _chunks(list(document_ids)):
        for document_id, requirement_id in session.execute(
                select(link.c.document_id, link.c.requirement_id)
                .where(link.c.document_id.in_(chunk)).order_by(link.c.document_id, link.c.requirement_id)):
            out[document_id].append(requirement_id)
    return out


def completeness_for(session, rows: list[tuple[str, str, str | None]], as_of: date) -> dict[str, CompletenessResult]:
    """rows: (customer_id, customer_type_id, risk_level). Uses calculate_completeness unchanged."""
    from app.models import Document

    specs = load_requirement_specs(session)
    docs: dict[str, list[dict]] = defaultdict(list)
    ids = [r[0] for r in rows]
    for chunk in _chunks(ids):
        drows = [dict(r) for r in session.execute(
            select(Document.document_id, Document.customer_id, Document.status, Document.expiry_date)
            .where(Document.customer_id.in_(chunk)).order_by(Document.document_id)).mappings()]
        req = requirement_ids_for(session, [d["document_id"] for d in drows])
        for d in drows:
            d["requirement_ids"] = tuple(req.get(d["document_id"], ()))
            docs[d["customer_id"]].append(d)
    return {
        cid: calculate_completeness(ctype, risk or "LOW", specs, docs.get(cid, []), as_of)
        for cid, ctype, risk in rows
    }


def ownership_summary(session, customer_ids: list[str] | None, as_of: date) -> dict[str, dict]:
    """{customer_id: {'total': Decimal, 'count': int}} over ACTIVE links (same rule as the detector)."""
    from app.models import OwnershipLink as L

    cols = (L.link_id, L.customer_id, L.ownership_pct, L.effective_from, L.effective_to)
    links: list[dict] = []
    if customer_ids is None:
        links = [dict(r) for r in session.execute(select(*cols)).mappings()]
    else:
        for chunk in _chunks(list(customer_ids)):
            links += [dict(r) for r in session.execute(select(*cols).where(L.customer_id.in_(chunk))).mappings()]
    totals = active_ownership_totals(links, as_of)
    counts: dict[str, int] = defaultdict(int)
    for l in links:
        if l["effective_from"] <= as_of and (l["effective_to"] is None or l["effective_to"] >= as_of):
            counts[l["customer_id"]] += 1
    return {cid: {"total": totals.get(cid, Decimal("0.00")), "count": counts.get(cid, 0)}
            for cid in set(totals) | set(counts)}


def document_view(row: dict, as_of: date, requirement_ids: list[str]) -> dict:
    expiry = row["expiry_date"]
    return {
        "document_id": row["document_id"], "customer_id": row["customer_id"], "file_name": row["file_name"],
        "file_hash": row["file_hash"], "file_size_bytes": row["file_size_bytes"], "issue_date": row["issue_date"],
        "expiry_date": expiry, "status": row["status"],
        "effective_state": document_state(row, as_of),
        "days_to_expiry": (expiry - as_of).days if expiry else None,
        "submitted_at": row["submitted_at"], "requirement_ids": requirement_ids,
    }


def document_columns():
    from app.models import Document as D
    return (D.document_id, D.customer_id, D.file_name, D.file_hash, D.file_size_bytes, D.issue_date,
            D.expiry_date, D.status, D.submitted_at)
