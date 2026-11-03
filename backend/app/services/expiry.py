"""Document expiry rules and expiry-alert lead times (pure functions)."""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ExpectedAlert:
    document_id: str
    customer_id: str
    alert_type: str            # EXPIRY_UPCOMING or DOCUMENT_EXPIRED
    lead_days: int | None      # the lead-time bucket for upcoming alerts, else None
    trigger_date: date         # the date the alert is raised
    expiry_date: date


def days_to_expiry(expiry: date, as_of: date) -> int:
    """Whole days from as_of to expiry (negative once expired)."""
    return (expiry - as_of).days


def lead_bucket(days_left: int, lead_times: Iterable[int]) -> int | None:
    """Tightest lead time already crossed, e.g. 45 days left with [90,60,30] -> 60.

    None if the document is further from expiry than the longest lead time,
    or already expired (days_left < 0).
    """
    if days_left < 0:
        return None
    crossed = [lead for lead in lead_times if days_left <= lead]
    return min(crossed) if crossed else None


def is_expired(expiry: date | None, as_of: date) -> bool:
    return expiry is not None and expiry < as_of


def expected_expiry_alerts(documents: Iterable[dict], as_of: date, lead_times: Iterable[int]) -> list[ExpectedAlert]:
    """Which expiry alerts SHOULD exist, derived only from documents.

    * VERIFIED and expiring within a lead time          -> EXPIRY_UPCOMING (one, tightest bucket)
    * VERIFIED or EXPIRED, expiry date already passed   -> DOCUMENT_EXPIRED
    Other statuses (pending, rejected, superseded) never raise expiry alerts.
    """
    lead_times = sorted(lead_times, reverse=True)
    result: list[ExpectedAlert] = []
    for d in documents:
        expiry = d["expiry_date"]
        if expiry is None or d["status"] not in ("VERIFIED", "EXPIRED"):
            continue
        if is_expired(expiry, as_of):
            result.append(ExpectedAlert(d["document_id"], d["customer_id"], "DOCUMENT_EXPIRED", None, expiry, expiry))
        elif d["status"] == "VERIFIED":
            lead = lead_bucket(days_to_expiry(expiry, as_of), lead_times)
            if lead is not None:
                from datetime import timedelta
                result.append(ExpectedAlert(d["document_id"], d["customer_id"], "EXPIRY_UPCOMING", lead,
                                            expiry - timedelta(days=lead), expiry))
    return sorted(result, key=lambda a: (a.trigger_date, a.alert_type, a.document_id))
