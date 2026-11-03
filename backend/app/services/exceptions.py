"""Exception management: run the detectors and keep exception alerts in sync.

An exception is an Alert whose type is one of the five anomaly types. Re-running the scan:
  * raises an alert for every NEW finding,
  * leaves existing alerts for findings that still hold untouched,
  * auto-resolves alerts whose finding no longer holds (the data was fixed).
Every change is written to the audit trail.
"""
import json
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, insert, select, update

from app.config import settings
from app.services.anomaly_detection import ISSUE_TYPES, Finding, run_all_detectors
from app.services.snapshot import Snapshot, load_snapshot
from generator import ids


def _next_number(session, column) -> int:
    last = session.scalar(select(func.max(column)))
    return int(last.rsplit("-", 1)[1]) + 1 if last else 1


def _key(alert_type: str, customer_id: str, document_id: str | None, message: str):
    return (alert_type, customer_id, document_id, message)


def run_exception_scan(session, as_of: date | None = None, snapshot: Snapshot | None = None) -> dict:
    from app.models import Alert, AuditEvent

    as_of = settings.as_of_date if as_of is None else as_of
    snap = snapshot or load_snapshot(session, as_of)
    findings: list[Finding] = run_all_detectors(snap)

    existing = session.execute(
        select(Alert.alert_id, Alert.alert_type, Alert.customer_id, Alert.document_id, Alert.message, Alert.status)
        .where(Alert.alert_type.in_(ISSUE_TYPES))
    ).all()
    existing_by_key = {_key(a.alert_type, a.customer_id, a.document_id, a.message): a for a in existing}
    finding_keys = {_key(f.issue_type, f.customer_id, f.document_id, f.reason): f for f in findings}

    next_alert = _next_number(session, Alert.alert_id)
    next_audit = _next_number(session, AuditEvent.event_id)
    when = datetime.combine(as_of, time(18, 0, 0))
    new_alerts, audit_rows, resolved_ids = [], [], []

    def audit(entity_id, action, new_value):
        nonlocal next_audit
        audit_rows.append({
            "event_id": ids.audit_event_id(as_of.year, next_audit), "entity_type": "alert", "entity_id": entity_id,
            "action": action, "old_value": None, "new_value": json.dumps(new_value, sort_keys=True),
            "actor": "anomaly_detector", "occurred_at": when + timedelta(seconds=next_audit % 3600),
        })
        next_audit += 1

    for key, f in sorted(finding_keys.items(), key=lambda kv: (kv[1].issue_type, kv[1].entity_id)):
        if key in existing_by_key:
            continue
        alert_id = ids.alert_id(as_of.year, next_alert)
        next_alert += 1
        new_alerts.append({
            "alert_id": alert_id, "customer_id": f.customer_id, "document_id": f.document_id,
            "alert_type": f.issue_type, "severity": f.severity, "status": "OPEN", "lead_days": None,
            "message": f.reason, "created_at": as_of, "resolved_at": None,
        })
        audit(alert_id, "ALERT_RAISED", {"alert_type": f.issue_type, "severity": f.severity})

    for key, a in existing_by_key.items():
        if key not in finding_keys and a.status != "RESOLVED":
            resolved_ids.append(a.alert_id)
            audit(a.alert_id, "ALERT_AUTO_RESOLVED", {"reason": "condition no longer detected"})

    if new_alerts:
        session.execute(insert(Alert), new_alerts)
    if resolved_ids:
        session.execute(update(Alert).where(Alert.alert_id.in_(resolved_ids)).values(status="RESOLVED", resolved_at=as_of))
    if audit_rows:
        session.execute(insert(AuditEvent), audit_rows)
    session.commit()
    return {
        "findings": findings,
        "alerts_raised": len(new_alerts),
        "alerts_auto_resolved": len(resolved_ids),
        "alerts_unchanged": len(finding_keys) - len(new_alerts),
    }
