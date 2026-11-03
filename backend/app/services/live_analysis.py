"""Live analysis for the API: one snapshot, with derived results cached.

The cache is keyed on cheap database fingerprints (alert and audit counts/max ids, which change whenever the
pipeline or an exception scan runs) plus a short time limit, so the API never serves stale numbers for long.
"""
import threading
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

from app.config import settings
from app.services.anomaly_detection import ISSUE_TYPES, run_all_detectors
from app.services.completeness import calculate_completeness, document_state
from app.services.snapshot import Snapshot, load_snapshot

TTL_SECONDS = 120
_cache: dict[str, tuple[tuple, float, object]] = {}
_lock = threading.Lock()


def _fingerprint(session) -> tuple:
    from app.models import Alert, AuditEvent
    return (id(session.get_bind()), settings.as_of_date,
            session.scalar(select(func.count()).select_from(Alert)), session.scalar(select(func.max(Alert.alert_id))),
            session.scalar(select(func.count()).select_from(AuditEvent)),
            session.scalar(select(func.max(AuditEvent.event_id))))


def _cached(session, name: str, build):
    key = _fingerprint(session)
    with _lock:
        hit = _cache.get(name)
        if hit and hit[0] == key and time.monotonic() - hit[1] < TTL_SECONDS:
            return hit[2]
    value = build()
    with _lock:
        _cache[name] = (key, time.monotonic(), value)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def get_snapshot(session) -> Snapshot:
    return _cached(session, "snapshot", lambda: load_snapshot(session))


def get_findings(session) -> list:
    return _cached(session, "findings", lambda: run_all_detectors(get_snapshot(session)))


def get_checks(session) -> list:
    from validation.checks import run_all_checks
    return _cached(session, "checks", lambda: run_all_checks(session, get_snapshot(session)))


def get_completeness(session) -> dict:
    """{customer_id: CompletenessResult} for every customer (same rule as everywhere else)."""
    def build():
        snap = get_snapshot(session)
        return {c["customer_id"]: calculate_completeness(
            c["customer_type_id"], snap.current_risk.get(c["customer_id"], "LOW"), snap.specs,
            snap.docs_by_customer.get(c["customer_id"], []), snap.as_of) for c in snap.customers}
    return _cached(session, "completeness", build)


def dashboard_summary(session) -> dict:
    from datetime import timedelta
    snap, comp = get_snapshot(session), get_completeness(session)
    as_of = snap.as_of

    def count(items, key):
        return dict(sorted(Counter(key(i) for i in items).items()))

    verified = [d for d in snap.documents if d["status"] == "VERIFIED" and d["expiry_date"]]
    expiring = {str(n): sum(1 for d in verified if as_of <= d["expiry_date"] <= as_of + timedelta(days=n))
                for n in (30, 60, 90)}
    approved = [c["customer_id"] for c in snap.customers if c["status"] == "APPROVED"]
    exc = [a for a in snap.alerts if a["alert_type"] in ISSUE_TYPES]
    return {
        "as_of_date": as_of,
        "customers": {"total": len(snap.customers), "by_status": count(snap.customers, lambda c: c["status"]),
                      "by_risk_level": count(snap.customers, lambda c: snap.current_risk.get(c["customer_id"], "UNRATED")),
                      "by_type": count(snap.customers, lambda c: c["customer_type_id"])},
        "completeness": {"by_label": count(comp.values(), lambda r: r.label), "approved_total": len(approved),
                         "approved_incomplete": sum(1 for cid in approved if comp[cid].percent < 100)},
        "documents": {"total": len(snap.documents), "by_status": count(snap.documents, lambda d: d["status"]),
                      "by_state": count(snap.documents, lambda d: document_state(d, as_of)),
                      "verified_expiring_within_days": expiring},
        "alerts": {"total": len(snap.alerts), "open": sum(1 for a in snap.alerts if a["status"] == "OPEN"),
                   "by_type": count(snap.alerts, lambda a: a["alert_type"]),
                   "by_severity": count(snap.alerts, lambda a: a["severity"]),
                   "by_status": count(snap.alerts, lambda a: a["status"])},
        "reviews": {"total": len(snap.reviews), "by_status": count(snap.reviews, lambda r: r["status"]),
                    "overdue": sum(1 for r in snap.reviews if r["due_date"] < as_of and r["status"] != "CLOSED"),
                    "due_next_30_days": sum(1 for r in snap.reviews if r["status"] != "CLOSED"
                                            and as_of <= r["due_date"] <= as_of + timedelta(days=30))},
        "exceptions": {"total": len(exc), "open": sum(1 for a in exc if a["status"] == "OPEN"),
                       "by_type": {t: sum(1 for a in exc if a["alert_type"] == t) for t in ISSUE_TYPES}},
    }
