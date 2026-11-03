"""KYC completeness, calculated from requirements and documents (never stored, never random)."""
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from app.services.requirements import RequirementSpec, applicable_requirements

# Reasons shown to users, strongest evidence first.
_PRIORITY = {"VALID": 0, "PENDING": 1, "EXPIRED": 2, "REJECTED": 3, "MISSING": 4}


@dataclass
class CompletenessResult:
    required: int
    satisfied: int
    percent: float
    label: str                                   # COMPLETE / INCOMPLETE / PENDING_VERIFICATION
    missing: list[dict] = field(default_factory=list)   # requirement_id, name, reason


def document_state(document: dict, as_of: date) -> str:
    """VALID, PENDING, EXPIRED, REJECTED or IGNORED for one document."""
    status = document["status"]
    expiry = document["expiry_date"]
    if status == "VERIFIED":
        return "EXPIRED" if (expiry is not None and expiry < as_of) else "VALID"
    if status == "EXPIRED":
        return "EXPIRED"
    if status == "SUBMITTED":
        return "PENDING"
    if status == "REJECTED":
        return "REJECTED"
    return "IGNORED"          # SUPERSEDED


def calculate_completeness(
    customer_type_id: str,
    risk_level: str,
    specs: Iterable[RequirementSpec],
    documents: Iterable[dict],
    as_of: date,
) -> CompletenessResult:
    """documents: dicts with document_id, status, expiry_date, requirement_ids (this customer's)."""
    required = applicable_requirements(customer_type_id, risk_level, specs, as_of, mandatory_only=True)
    best: dict[str, tuple[str, dict | None]] = {s.requirement_id: ("MISSING", None) for s in required}
    for doc in documents:
        state = document_state(doc, as_of)
        if state == "IGNORED":
            continue
        for requirement_id in doc["requirement_ids"]:
            if requirement_id in best and _PRIORITY[state] < _PRIORITY[best[requirement_id][0]]:
                best[requirement_id] = (state, doc)

    satisfied = 0
    missing = []
    for spec in required:
        state, doc = best[spec.requirement_id]
        if state == "VALID":
            satisfied += 1
            continue
        reason = {
            "MISSING": "No document submitted",
            "PENDING": "Document pending verification",
            "EXPIRED": f"Document expired on {doc['expiry_date']}" if doc and doc["expiry_date"] else "Document expired",
            "REJECTED": "Document rejected",
        }[state]
        missing.append({"requirement_id": spec.requirement_id, "name": spec.name, "state": state, "reason": reason})

    percent = 100.0 if not required else round(100.0 * satisfied / len(required), 1)
    if satisfied == len(required):
        label = "COMPLETE"
    elif missing and all(m["state"] == "PENDING" for m in missing):
        label = "PENDING_VERIFICATION"
    else:
        label = "INCOMPLETE"
    return CompletenessResult(len(required), satisfied, percent, label, missing)
