"""Step 3C: documents, verification history and document-requirement links.

Rules (decision D14): every APPROVED customer gets complete, verified, unexpired
evidence for every mandatory requirement. Other customers get partial evidence.
The total is topped up to exactly n_documents with history documents
(superseded earlier versions and rejected earlier attempts).

Run from the backend folder (after python -m generator.customers):
    python -m generator.documents
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.config import settings
from app.services.dateutils import add_months
from app.services.requirements import RequirementSpec, applicable_requirements
from generator import ids
from generator.rng import make_rng, sha256_hex

# ---- tunable rules (all documented in docs/assumptions_and_rules.md later) ----------

# Each customer gets a personal "how much evidence have they supplied" level from this range.
PRESENCE_RANGE = {
    "APPROVED": (1.0, 1.0),
    "SUSPENDED": (0.6, 1.0),
    "CLOSED": (0.6, 1.0),
    "UNDER_REVIEW": (0.1, 0.7),
    "PROSPECT": (0.0, 0.24),
}
OPTIONAL_PRESENCE = 0.10   # chance an optional requirement has a document

# State of a current document, by customer status.
STATE_WEIGHTS = {
    "APPROVED": {"VERIFIED": 1.0},
    "SUSPENDED": {"VERIFIED": 0.5, "EXPIRED": 0.4, "REJECTED": 0.1},
    "CLOSED": {"VERIFIED": 0.7, "EXPIRED": 0.3},
    "UNDER_REVIEW": {"VERIFIED": 0.5, "SUBMITTED": 0.28, "REJECTED": 0.12, "EXPIRED": 0.10},
    "PROSPECT": {"SUBMITTED": 0.6, "VERIFIED": 0.2, "REJECTED": 0.1, "EXPIRED": 0.1},
}

# One document that satisfies two requirements (demonstrates the N:M bridge table).
BUNDLES = [("Register of directors and shareholders", "Beneficial ownership declaration", 0.25)]

SOON_WINDOW_DAYS = 90            # "expiring soon" = within the longest alert lead time
SOON_SHARE_SHORT_VALIDITY = 0.10
SOON_SHARE_LONG_VALIDITY = 0.03
PRELUDE_PENDING_SHARE = 0.25     # verified docs that also show an earlier PENDING event
VERIFIERS = [f"analyst_{i:02d}" for i in range(1, 9)]
REJECTION_REASONS = ["Image unreadable", "Name does not match application", "Document incomplete"]
EXTRA_SOURCE_STATES = {"VERIFIED", "SUBMITTED", "REJECTED"}


@dataclass
class _Doc:
    customer_id: str
    customer_number: int
    created_at: date
    requirement_ids: tuple[str, ...]
    name_slug: str
    validity_months: int | None
    state: str
    issue: date
    expiry: date | None
    submitted: date
    variant: int = 0                      # 0 = current document, 1 = history document
    events: list[tuple] = field(default_factory=list)   # (result, verified_at, by, notes)


@dataclass
class GeneratedDocuments:
    documents: list[dict]
    verifications: list[dict]
    links: list[dict]


def specs_from_seed_data() -> list[RequirementSpec]:
    """Requirement specs built from the seed constants (no database needed)."""
    from app.seed_reference import REQUIREMENTS, SEED_EFFECTIVE_FROM, requirement_id

    return [
        RequirementSpec(
            requirement_id=requirement_id(position),
            name=s["name"],
            is_mandatory=s["mandatory"],
            min_risk_level=s["min_risk"],
            validity_months=s["validity_months"],
            effective_from=SEED_EFFECTIVE_FROM,
            effective_to=None,
            customer_type_ids=frozenset(s["applies_to"]),
        )
        for position, s in enumerate(REQUIREMENTS, start=1)
    ]


# ---------------------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _make_bundles(applicable: list[RequirementSpec], rng) -> list[tuple[RequirementSpec, ...]]:
    """Group requirements into documents; most are one-to-one, some combos share a document."""
    by_name = {s.name: s for s in applicable}
    used: set[str] = set()
    bundles: list[tuple[RequirementSpec, ...]] = []
    for name_a, name_b, probability in BUNDLES:
        a, b = by_name.get(name_a), by_name.get(name_b)
        if a and b and a.validity_months == b.validity_months and rng.random() < probability:
            bundles.append((a, b))
            used.update({a.requirement_id, b.requirement_id})
    for spec in applicable:
        if spec.requirement_id not in used:
            bundles.append((spec,))
    bundles.sort(key=lambda bundle: bundle[0].requirement_id)
    return bundles


def _choose_state(status: str, limited: bool, rng) -> str:
    weights = STATE_WEIGHTS[status]
    state = rng.choices(list(weights), list(weights.values()))[0]
    if state == "EXPIRED" and not limited:
        return "VERIFIED"        # a document without an expiry rule cannot expire
    return state


def _days_until_expiry(validity_months: int, rng) -> int:
    soon_share = SOON_SHARE_SHORT_VALIDITY if validity_months <= 24 else SOON_SHARE_LONG_VALIDITY
    if rng.random() < soon_share:
        return rng.randint(1, SOON_WINDOW_DAYS)
    return rng.randint(SOON_WINDOW_DAYS + 1, validity_months * 28)


def _dates_for_state(state, validity, created_at, as_of, rng):
    """Return (issue_date, expiry_date, submitted_at) for a current document."""
    limited = validity is not None
    if state == "VERIFIED":
        if limited:
            expiry = as_of + timedelta(days=_days_until_expiry(validity, rng))
            issue = add_months(expiry, -validity)
            submitted = min(as_of, max(created_at, issue + timedelta(days=rng.randint(0, 10))))
        else:
            issue = created_at - timedelta(days=rng.randint(30, 3650))
            expiry = None
            submitted = min(as_of, created_at + timedelta(days=rng.randint(0, 20)))
    elif state == "EXPIRED":
        expiry = as_of - timedelta(days=rng.randint(1, 180))
        issue = add_months(expiry, -validity)
        submitted = min(as_of, max(created_at, issue + timedelta(days=rng.randint(0, 10))))
    else:  # SUBMITTED or REJECTED: a recent upload
        recent = rng.randint(0, 25) if state == "SUBMITTED" else rng.randint(5, 90)
        submitted = max(created_at, as_of - timedelta(days=recent))
        issue = submitted - timedelta(days=rng.randint(0, 20))
        expiry = add_months(issue, validity) if limited else None
    return issue, expiry, submitted


def _datetime_on(day: date, rng) -> datetime:
    return datetime(day.year, day.month, day.day, rng.randint(9, 17), rng.randint(0, 59))


def _events_for(state, submitted, as_of, rng) -> list[tuple]:
    """Verification event history for one document, oldest first."""
    pending = ("PENDING", None, None, "Awaiting verification")
    if state == "SUBMITTED":
        return [pending]
    verified_on = min(as_of, submitted + timedelta(days=rng.randint(1, 5)))
    by = rng.choice(VERIFIERS)
    if state == "REJECTED":
        return [("REJECTED", _datetime_on(verified_on, rng), by, rng.choice(REJECTION_REASONS))]
    events = []
    if rng.random() < PRELUDE_PENDING_SHARE:
        events.append(pending)
    events.append(("VERIFIED", _datetime_on(verified_on, rng), by, "Document verified"))
    return events


def generate_documents(
    customers: list[dict],
    current_risk: dict[str, str],
    specs: list[RequirementSpec],
    n_documents: int | None = None,
    seed: int | None = None,
    as_of: date | None = None,
) -> GeneratedDocuments:
    n_documents = settings.n_documents if n_documents is None else n_documents
    as_of = settings.as_of_date if as_of is None else as_of
    master_seed = settings.seed if seed is None else seed

    rng = make_rng("documents", seed)
    extra_rng = make_rng("document_extras", seed)

    # ---- 1. current documents, driven by the customer's real requirements -------------
    base: list[_Doc] = []
    for customer in customers:
        customer_id = customer["customer_id"]
        status = customer["status"]
        applicable = applicable_requirements(
            customer["customer_type_id"], current_risk[customer_id], specs, as_of
        )
        low, high = PRESENCE_RANGE[status]
        presence = rng.uniform(low, high) if high > low else low

        for bundle in _make_bundles(applicable, rng):
            mandatory = any(s.is_mandatory for s in bundle)
            if not (rng.random() < (presence if mandatory else OPTIONAL_PRESENCE)):
                continue
            validity = bundle[0].validity_months
            state = _choose_state(status, validity is not None, rng)
            issue, expiry, submitted = _dates_for_state(
                state, validity, customer["created_at"], as_of, rng
            )
            doc = _Doc(
                customer_id=customer_id,
                customer_number=ids.parse_customer_number(customer_id),
                created_at=customer["created_at"],
                requirement_ids=tuple(s.requirement_id for s in bundle),
                name_slug="-".join(_slug(s.name) for s in bundle),
                validity_months=validity,
                state=state, issue=issue, expiry=expiry, submitted=submitted,
            )
            doc.events = _events_for(state, submitted, as_of, rng)
            base.append(doc)

    # ---- 2. top up to exactly n_documents with history documents ----------------------
    needed = n_documents - len(base)
    if needed < 0:
        raise ValueError(
            f"Baseline needs {len(base)} documents, more than n_documents={n_documents}. "
            "Lower the evidence coverage or raise n_documents."
        )
    eligible = [i for i, d in enumerate(base) if d.state in EXTRA_SOURCE_STATES]
    if needed > len(eligible):
        raise ValueError(f"Need {needed} history documents but only {len(eligible)} sources exist.")
    extras = [_history_doc(base[i], as_of, extra_rng) for i in extra_rng.sample(eligible, needed)]

    # ---- 3. assign final IDs, in a stable chronological order per customer ------------
    per_customer: dict[str, list[_Doc]] = {}
    for doc in base + extras:
        per_customer.setdefault(doc.customer_id, []).append(doc)

    documents, verifications, links = [], [], []
    for customer_id in sorted(per_customer):
        docs = sorted(per_customer[customer_id], key=lambda d: (d.submitted, d.requirement_ids, d.variant))
        for sequence, doc in enumerate(docs, start=1):
            document_id = ids.document_id(doc.customer_number, sequence)
            fingerprint = f"{master_seed}|{customer_id}|{'+'.join(doc.requirement_ids)}|v{doc.variant}"
            documents.append({
                "document_id": document_id,
                "customer_id": customer_id,
                "file_name": f"{doc.name_slug}_{customer_id.lower()}_v{doc.variant + 1}.pdf",
                "file_hash": sha256_hex(fingerprint),
                "file_size_bytes": 40_000 + (int(sha256_hex("size" + fingerprint)[:8], 16) % 3_460_000),
                "issue_date": doc.issue,
                "expiry_date": doc.expiry,
                "status": doc.state,
                "submitted_at": doc.submitted,
            })
            for requirement_id in doc.requirement_ids:
                links.append({"document_id": document_id, "requirement_id": requirement_id})
            for event_number, (result, verified_at, by, notes) in enumerate(doc.events, start=1):
                verifications.append({
                    "verification_id": ids.verification_id(doc.customer_number, sequence, event_number),
                    "document_id": document_id,
                    "result": result,
                    "verified_by": by,
                    "verified_at": verified_at,
                    "notes": notes,
                })
    return GeneratedDocuments(documents, verifications, links)


def _history_doc(source: _Doc, as_of: date, rng) -> _Doc:
    """An earlier version of the same evidence: superseded if renewed, else a rejected attempt."""
    validity = source.validity_months
    if source.state == "VERIFIED" and validity is not None:
        prior_issue = add_months(source.issue, -validity)
        prior_submitted = prior_issue + timedelta(days=rng.randint(0, 10))
        if prior_submitted >= source.created_at:
            return _Doc(
                customer_id=source.customer_id, customer_number=source.customer_number,
                created_at=source.created_at, requirement_ids=source.requirement_ids,
                name_slug=source.name_slug, validity_months=validity, state="SUPERSEDED",
                issue=prior_issue, expiry=source.issue, submitted=prior_submitted, variant=1,
                events=_events_for("SUPERSEDED", prior_submitted, as_of, rng),
            )
    submitted = max(source.created_at, source.submitted - timedelta(days=rng.randint(3, 30)))
    issue = min(source.issue - timedelta(days=rng.randint(1, 30)), submitted)
    expiry = add_months(issue, validity) if validity is not None else None
    return _Doc(
        customer_id=source.customer_id, customer_number=source.customer_number,
        created_at=source.created_at, requirement_ids=source.requirement_ids,
        name_slug=source.name_slug, validity_months=validity, state="REJECTED",
        issue=issue, expiry=expiry, submitted=submitted, variant=1,
        events=_events_for("REJECTED", submitted, as_of, rng),
    )


# ---------------------------------------------------------------------------------------

def load_documents(session, data: GeneratedDocuments) -> dict[str, int]:
    """Bulk-insert documents, then their verification events and requirement links."""
    from sqlalchemy import insert

    from app.models import Document, Verification, document_requirement_link

    session.execute(insert(Document), data.documents)
    session.execute(insert(Verification), data.verifications)
    session.execute(insert(document_requirement_link), data.links)
    session.commit()
    return {
        "document": len(data.documents),
        "verification": len(data.verifications),
        "document_requirement_link": len(data.links),
    }


def read_customers(session) -> tuple[list[dict], dict[str, str]]:
    """Read customers and their CURRENT risk level back from the database."""
    from sqlalchemy import select

    from app.models import Customer, RiskRating

    customers = [
        dict(row) for row in session.execute(
            select(Customer.customer_id, Customer.customer_type_id, Customer.status, Customer.created_at)
            .order_by(Customer.customer_id)
        ).mappings()
    ]
    current_risk = dict(session.execute(
        select(RiskRating.customer_id, RiskRating.level).where(RiskRating.effective_to.is_(None))
    ).all())
    return customers, current_risk


def main() -> None:
    from collections import Counter

    from app.database import Base, SessionLocal, engine
    from app.services.requirements import load_requirement_specs
    from generator.db_utils import clear_tables

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        customers, current_risk = read_customers(session)
        if not customers:
            raise SystemExit("No customers found. Run: python -m generator.customers")
        specs = load_requirement_specs(session)
        clear_tables(session, ["alert", "verification", "document_requirement_link", "document"])
        data = generate_documents(customers, current_risk, specs)
        counts = load_documents(session, data)

    print(f"Inserted: {counts}")
    print("Document status:", dict(Counter(d["status"] for d in data.documents)))
    print("Documents linked to 2 requirements:", sum(1 for k, v in Counter(l["document_id"] for l in data.links).items() if v == 2))


if __name__ == "__main__":
    main()
