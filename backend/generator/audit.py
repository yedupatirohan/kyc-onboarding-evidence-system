"""Step 3E-c: append-only audit trail of important state changes."""
import json
from datetime import date, datetime

from app.config import settings
from generator import ids
from generator.rng import make_rng

APPROVERS = [f"approver_{i:02d}" for i in range(1, 5)]
ANALYSTS = [f"analyst_{i:02d}" for i in range(1, 9)]
ONBOARDED = {"APPROVED", "SUSPENDED", "CLOSED"}


def _json(value) -> str | None:
    return None if value is None else json.dumps(value, sort_keys=True, default=str)


def _at(day: date, hour: int, rng) -> datetime:
    return datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), rng.randint(0, 59))


def generate_audit_events(customers, risk_ratings, documents, verifications, reviews, alerts,
                          seed=None, as_of=None, year=None) -> list[dict]:
    from datetime import timedelta

    as_of = settings.as_of_date if as_of is None else as_of
    year = as_of.year if year is None else year
    rng = make_rng("audit", seed)
    events: list[dict] = []

    def add(entity_type, entity_id, action, old, new, actor, when):
        events.append({"entity_type": entity_type, "entity_id": entity_id, "action": action,
                       "old_value": _json(old), "new_value": _json(new), "actor": actor, "occurred_at": when})

    for c in customers:
        cid, status, created = c["customer_id"], c["status"], c["created_at"]
        add("customer", cid, "CUSTOMER_CREATED", None, {"status": "PROSPECT"}, "system", _at(created, 8, rng))
        if status == "PROSPECT":
            continue
        onboarded_like = status in ONBOARDED
        review_day = min(as_of, created + timedelta(days=rng.randint(0, 2) if onboarded_like else rng.randint(1, 10)))
        add("customer", cid, "STATUS_CHANGED", {"status": "PROSPECT"}, {"status": "UNDER_REVIEW"},
            rng.choice(ANALYSTS), _at(review_day, 10, rng))
        if onboarded_like:
            add("customer", cid, "STATUS_CHANGED", {"status": "UNDER_REVIEW"}, {"status": "APPROVED"},
                rng.choice(APPROVERS), _at(c["onboarded_at"], 14, rng))
            if status == "SUSPENDED":
                day = min(as_of, c["onboarded_at"] + timedelta(days=rng.randint(15, 200)))
                add("customer", cid, "STATUS_CHANGED", {"status": "APPROVED"}, {"status": "SUSPENDED"},
                    rng.choice(APPROVERS), _at(day, 15, rng))
            elif status == "CLOSED":
                day = min(as_of, c["onboarded_at"] + timedelta(days=rng.randint(15, 300)))
                add("customer", cid, "STATUS_CHANGED", {"status": "APPROVED"}, {"status": "CLOSED"},
                    rng.choice(APPROVERS), _at(day, 15, rng))

    ratings_by_customer: dict[str, list[dict]] = {}
    for r in sorted(risk_ratings, key=lambda r: (r["customer_id"], r["effective_from"])):
        ratings_by_customer.setdefault(r["customer_id"], []).append(r)
    for cid, ratings in ratings_by_customer.items():
        for before, after in zip(ratings, ratings[1:]):
            add("risk_rating", after["rating_id"], "RISK_RATING_CHANGED",
                {"level": before["level"], "score": before["score"]},
                {"level": after["level"], "score": after["score"]},
                rng.choice(ANALYSTS), _at(after["effective_from"], 11, rng))

    for d in documents:
        add("document", d["document_id"], "DOCUMENT_SUBMITTED", None, {"status": "SUBMITTED"},
            "customer_portal", _at(d["submitted_at"], rng.randint(8, 18), rng))
    for v in verifications:
        if v["verified_at"] is not None:
            action = "DOCUMENT_VERIFIED" if v["result"] == "VERIFIED" else "DOCUMENT_REJECTED"
            add("document", v["document_id"], action, {"status": "SUBMITTED"}, {"result": v["result"]},
                v["verified_by"], v["verified_at"])
    for r in reviews:
        if r["status"] == "CLOSED":
            add("review_case", r["review_id"], "REVIEW_CLOSED", {"status": "OPEN"},
                {"status": "CLOSED", "resolution": r["resolution"]}, r["closed_by"], _at(r["closed_at"], 16, rng))
    for a in alerts:
        add("alert", a["alert_id"], "ALERT_RAISED", None,
            {"alert_type": a["alert_type"], "severity": a["severity"]}, "system", _at(a["created_at"], 6, rng))

    events.sort(key=lambda e: (e["occurred_at"], e["entity_type"], e["entity_id"], e["action"]))
    for number, e in enumerate(events, start=1):
        e["event_id"] = ids.audit_event_id(year, number)
    return events
