"""Step 3E-b: expiry and overdue-review alerts, derived from documents and reviews."""
from datetime import date, timedelta

from app.config import settings
from app.services.expiry import expected_expiry_alerts
from generator import ids
from generator.rng import make_rng

STATUS_WEIGHTS = {"OPEN": 0.70, "ACKNOWLEDGED": 0.20, "RESOLVED": 0.10}


def upcoming_severity(lead_days: int) -> str:
    if lead_days <= 30:
        return "HIGH"
    if lead_days <= 60:
        return "MEDIUM"
    return "LOW"


def generate_alerts(documents, reviews, seed=None, as_of=None, lead_times=None, year=None) -> list[dict]:
    as_of = settings.as_of_date if as_of is None else as_of
    lead_times = settings.alert_lead_times if lead_times is None else lead_times
    year = as_of.year if year is None else year
    rng = make_rng("alerts", seed)

    items = []   # (created_at, type, customer_id, document_id, lead_days, severity, message)
    for a in expected_expiry_alerts(documents, as_of, lead_times):
        if a.alert_type == "EXPIRY_UPCOMING":
            message = (f"Document {a.document_id} expires on {a.expiry_date}: "
                       f"{a.lead_days}-day expiry warning.")
            items.append((a.trigger_date, a.alert_type, a.customer_id, a.document_id, a.lead_days,
                          upcoming_severity(a.lead_days), message))
        else:
            message = f"Document {a.document_id} expired on {a.expiry_date}."
            items.append((a.trigger_date, a.alert_type, a.customer_id, a.document_id, None, "HIGH", message))
    for r in reviews:
        if r["status"] == "OVERDUE":
            items.append((r["due_date"] + timedelta(days=1), "REVIEW_OVERDUE", r["customer_id"], None, None,
                          "MEDIUM", f"Review {r['review_id']} was due on {r['due_date']} and is still open."))

    items.sort(key=lambda i: (i[0], i[1], i[2], i[3] or ""))
    states, weights = list(STATUS_WEIGHTS), list(STATUS_WEIGHTS.values())
    alerts = []
    for number, (created, kind, customer_id, document_id, lead, severity, message) in enumerate(items, start=1):
        status = rng.choices(states, weights)[0]
        resolved = min(as_of, created + timedelta(days=rng.randint(1, 30))) if status == "RESOLVED" else None
        alerts.append({
            "alert_id": ids.alert_id(year, number),
            "customer_id": customer_id,
            "document_id": document_id,
            "alert_type": kind,
            "severity": severity,
            "status": status,
            "lead_days": lead,
            "message": message,
            "created_at": created,
            "resolved_at": resolved,
        })
    return alerts
