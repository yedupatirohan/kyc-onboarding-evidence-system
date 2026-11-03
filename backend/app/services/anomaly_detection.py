"""Detectors for the five mandatory negative scenarios.

IMPORTANT: these functions read ONLY operational data (a Snapshot). They never import or
read the ground-truth labels, so detection quality can be measured honestly.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.completeness import calculate_completeness
from app.services.snapshot import Snapshot

EXPIRED_MARKED_VALID = "EXPIRED_MARKED_VALID"
APPROVED_MISSING_EVIDENCE = "APPROVED_MISSING_EVIDENCE"
OWNERSHIP_OVER_100 = "OWNERSHIP_OVER_100"
REVIEW_CLOSED_NO_RESOLUTION = "REVIEW_CLOSED_NO_RESOLUTION"
DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
ISSUE_TYPES = [EXPIRED_MARKED_VALID, APPROVED_MISSING_EVIDENCE, OWNERSHIP_OVER_100,
               REVIEW_CLOSED_NO_RESOLUTION, DUPLICATE_DOCUMENT]

SEVERITY = {
    EXPIRED_MARKED_VALID: "HIGH", APPROVED_MISSING_EVIDENCE: "CRITICAL", OWNERSHIP_OVER_100: "HIGH",
    REVIEW_CLOSED_NO_RESOLUTION: "MEDIUM", DUPLICATE_DOCUMENT: "HIGH",
}
EXPECTED_DECISION = {
    EXPIRED_MARKED_VALID: "Downgrade the document to EXPIRED, request a fresh document and mark the customer Requires Review.",
    APPROVED_MISSING_EVIDENCE: "Suspend the approval until every mandatory document is supplied and verified.",
    OWNERSHIP_OVER_100: "Block approval and obtain a corrected beneficial ownership declaration.",
    REVIEW_CLOSED_NO_RESOLUTION: "Reopen the review and record a resolution before closing it again.",
    DUPLICATE_DOCUMENT: "Escalate to compliance for possible document fraud; request original documents from both customers.",
}
RULES = {
    EXPIRED_MARKED_VALID: "document.status = VERIFIED AND document.expiry_date < as_of_date",
    APPROVED_MISSING_EVIDENCE: "customer.status = APPROVED AND completeness of mandatory requirements < 100%",
    OWNERSHIP_OVER_100: "SUM(ownership_pct) over ACTIVE ownership links of a business > 100.00",
    REVIEW_CLOSED_NO_RESOLUTION: "review.status = CLOSED AND resolution is empty",
    DUPLICATE_DOCUMENT: "same file_hash on documents of two customers that share no beneficial owner",
}


@dataclass(frozen=True)
class Finding:
    issue_type: str
    entity_type: str          # document / customer / review_case
    entity_id: str
    customer_id: str
    document_id: str | None
    severity: str
    reason: str
    expected_decision: str


def _finding(issue, entity_type, entity_id, customer_id, reason, document_id=None) -> Finding:
    return Finding(issue, entity_type, entity_id, customer_id, document_id, SEVERITY[issue], reason, EXPECTED_DECISION[issue])


def detect_expired_marked_valid(documents: list[dict], as_of: date) -> list[Finding]:
    return [
        _finding(EXPIRED_MARKED_VALID, "document", d["document_id"], d["customer_id"],
                 f"Document {d['document_id']} is marked VERIFIED but expired on {d['expiry_date']} (as of {as_of}).",
                 d["document_id"])
        for d in documents
        if d["status"] == "VERIFIED" and d["expiry_date"] is not None and d["expiry_date"] < as_of
    ]


def detect_approved_missing_evidence(snap: Snapshot) -> list[Finding]:
    findings = []
    for c in snap.customers:
        if c["status"] != "APPROVED":
            continue
        result = calculate_completeness(
            c["customer_type_id"], snap.current_risk[c["customer_id"]], snap.specs,
            snap.docs_by_customer.get(c["customer_id"], []), snap.as_of)
        if result.percent < 100.0:
            names = ", ".join(m["name"] for m in result.missing[:3])
            more = f" and {len(result.missing) - 3} more" if len(result.missing) > 3 else ""
            findings.append(_finding(
                APPROVED_MISSING_EVIDENCE, "customer", c["customer_id"], c["customer_id"],
                f"Customer {c['customer_id']} is APPROVED but only {result.satisfied} of {result.required} "
                f"mandatory requirements are satisfied ({result.percent}%). Missing: {names}{more}."))
    return findings


def active_ownership_totals(owner_links: list[dict], as_of: date) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for l in owner_links:
        if l["effective_from"] <= as_of and (l["effective_to"] is None or l["effective_to"] >= as_of):
            totals[l["customer_id"]] += Decimal(str(l["ownership_pct"])).quantize(Decimal("0.01"))
    return dict(totals)


def detect_ownership_over_100(owner_links: list[dict], as_of: date) -> list[Finding]:
    return [
        _finding(OWNERSHIP_OVER_100, "customer", customer_id, customer_id,
                 f"Active beneficial ownership of {customer_id} adds up to {total}%, which exceeds 100%.")
        for customer_id, total in sorted(active_ownership_totals(owner_links, as_of).items())
        if total > Decimal("100.00")
    ]


def detect_review_closed_no_resolution(reviews: list[dict]) -> list[Finding]:
    return [
        _finding(REVIEW_CLOSED_NO_RESOLUTION, "review_case", r["review_id"], r["customer_id"],
                 f"Review {r['review_id']} was closed on {r['closed_at']} without a recorded resolution.")
        for r in reviews
        if r["status"] == "CLOSED" and not (r["resolution"] or "").strip()
    ]


def detect_duplicate_documents(documents: list[dict], owner_links: list[dict]) -> list[Finding]:
    owners_of: dict[str, set[str]] = defaultdict(set)
    for l in owner_links:                               # any period counts as "related"
        owners_of[l["customer_id"]].add(l["owner_id"])
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for d in documents:
        by_hash[d["file_hash"]].append(d)

    findings = []
    for file_hash, docs in sorted(by_hash.items()):
        customers = sorted({d["customer_id"] for d in docs})
        if len(customers) < 2:
            continue
        for d in docs:
            partners = [c for c in customers if c != d["customer_id"]
                        and not (owners_of[d["customer_id"]] & owners_of[c])]
            if partners:
                findings.append(_finding(
                    DUPLICATE_DOCUMENT, "document", d["document_id"], d["customer_id"],
                    f"Document {d['document_id']} has the same file hash as documents of unrelated "
                    f"customer(s) {', '.join(partners)}.", d["document_id"]))
    return findings


def run_all_detectors(snap: Snapshot) -> list[Finding]:
    findings = (
        detect_expired_marked_valid(snap.documents, snap.as_of)
        + detect_approved_missing_evidence(snap)
        + detect_ownership_over_100(snap.owner_links, snap.as_of)
        + detect_review_closed_no_resolution(snap.reviews)
        + detect_duplicate_documents(snap.documents, snap.owner_links)
    )
    return sorted(findings, key=lambda f: (f.issue_type, f.entity_id))
