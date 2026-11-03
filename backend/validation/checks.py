"""Automated data-quality checks. Each returns a CheckResult; 0 violations = pass."""
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text

from app.database import Base
from app.enums import (AlertSeverity, AlertStatus, AlertType, CustomerStatus, DocumentStatus,
                       ReviewStatus, RiskLevel, VerificationResult)
from app.services.anomaly_detection import active_ownership_totals
from app.services.completeness import calculate_completeness
from app.services.expiry import expected_expiry_alerts
from app.services.review_schedule import expected_status
from app.services.risk import risk_level_for_score
from app.services.snapshot import Snapshot
from generator.ids import PATTERNS

ALLOWED_VALUES = {
    ("customer", "status"): CustomerStatus, ("document", "status"): DocumentStatus,
    ("verification", "result"): VerificationResult, ("review_case", "status"): ReviewStatus,
    ("alert", "alert_type"): AlertType, ("alert", "severity"): AlertSeverity,
    ("alert", "status"): AlertStatus, ("risk_rating", "level"): RiskLevel,
    ("kyc_requirement", "min_risk_level"): RiskLevel,
}
ID_COLUMNS = {
    ("customer", "customer_id"): "customer", ("document", "document_id"): "document",
    ("review_case", "review_id"): "review", ("alert", "alert_id"): "alert",
    ("risk_rating", "rating_id"): "risk_rating", ("verification", "verification_id"): "verification",
    ("beneficial_owner", "owner_id"): "owner", ("ownership_link", "link_id"): "ownership_link",
    ("audit_event", "event_id"): "audit_event", ("kyc_requirement", "requirement_id"): "requirement",
}
ALLOWED_TRANSITIONS = {
    ("PROSPECT", "UNDER_REVIEW"), ("UNDER_REVIEW", "APPROVED"), ("UNDER_REVIEW", "PROSPECT"),
    ("APPROVED", "SUSPENDED"), ("APPROVED", "CLOSED"), ("SUSPENDED", "APPROVED"), ("SUSPENDED", "CLOSED"),
}
BUSINESS_TYPES = {"COMPANY", "TRUST"}


@dataclass
class CheckResult:
    name: str
    description: str
    violations: int
    samples: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.violations == 0


def _result(name, description, bad: list[str]) -> CheckResult:
    return CheckResult(name, description, len(bad), bad[:5])


def check_primary_keys(session) -> CheckResult:
    bad = []
    for table in Base.metadata.sorted_tables:
        cols = ", ".join(c.name for c in table.primary_key.columns)
        n = session.execute(text(f"SELECT COUNT(*) FROM (SELECT 1 FROM {table.name} GROUP BY {cols} HAVING COUNT(*) > 1)")).scalar()
        if n:
            bad.append(f"{table.name}: {n} duplicate keys")
    return _result("primary_key_uniqueness", "No duplicate primary keys in any table", bad)


def check_foreign_keys(session) -> CheckResult:
    rows = session.execute(text("PRAGMA foreign_key_check")).all() if session.get_bind().dialect.name == "sqlite" else []
    return _result("foreign_key_integrity", "Every foreign key points at an existing parent row", [str(r) for r in rows])


def check_enum_values(session) -> CheckResult:
    bad = []
    for (table, column), enum_cls in ALLOWED_VALUES.items():
        allowed = {m.value for m in enum_cls}
        for (value,) in session.execute(text(f"SELECT DISTINCT {column} FROM {table}")):
            if value not in allowed:
                bad.append(f"{table}.{column}: {value!r}")
    return _result("allowed_enum_values", "All status/level/type columns hold allowed values only", bad)


def check_id_formats(session) -> CheckResult:
    bad = []
    for (table, column), pattern in ID_COLUMNS.items():
        for (value,) in session.execute(text(f"SELECT {column} FROM {table}")):
            if not PATTERNS[pattern].fullmatch(value):
                bad.append(f"{table}.{column}: {value}")
    return _result("id_format", "All identifiers follow the required formats", bad)


def check_date_ordering(session, as_of: date) -> CheckResult:
    queries = {
        "document issue_date after submitted_at": "SELECT COUNT(*) FROM document WHERE issue_date > submitted_at",
        "document submitted after as_of": "SELECT COUNT(*) FROM document WHERE submitted_at > :a",
        "document expiry before issue": "SELECT COUNT(*) FROM document WHERE expiry_date < issue_date",
        "customer onboarded before created": "SELECT COUNT(*) FROM customer WHERE onboarded_at < created_at",
        "review closed before opened": "SELECT COUNT(*) FROM review_case WHERE closed_at < opened_at",
        "alert resolved before created": "SELECT COUNT(*) FROM alert WHERE resolved_at < created_at",
        "alert created after as_of": "SELECT COUNT(*) FROM alert WHERE created_at > :a",
        "ownership end before start": "SELECT COUNT(*) FROM ownership_link WHERE effective_to < effective_from",
        "risk rating end before start": "SELECT COUNT(*) FROM risk_rating WHERE effective_to < effective_from",
    }
    bad = []
    for label, sql in queries.items():
        n = session.execute(text(sql), {"a": as_of}).scalar()
        if n:
            bad.append(f"{label}: {n}")
    return _result("date_ordering", "Dates are in a possible order and never in the future", bad)


def check_ownership_reconciliation(snap: Snapshot) -> CheckResult:
    totals = active_ownership_totals(snap.owner_links, snap.as_of)
    bad = []
    for c in snap.customers:
        if c["customer_type_id"] in BUSINESS_TYPES:
            total = totals.get(c["customer_id"])
            if total is None or str(total) != "100.00":
                bad.append(f"{c['customer_id']}: active ownership {total}")
    return _result("ownership_reconciliation", "Every business's active ownership adds up to exactly 100.00%", bad)


def check_lifecycle_transitions(session, snap: Snapshot) -> CheckResult:
    changes = defaultdict(list)
    for entity_id, new_value in session.execute(text(
            "SELECT entity_id, new_value FROM audit_event WHERE action = 'STATUS_CHANGED' "
            "ORDER BY occurred_at, event_id")):
        changes[entity_id].append(json.loads(new_value)["status"])
    bad = []
    for c in snap.customers:
        path = ["PROSPECT"] + changes.get(c["customer_id"], [])
        for before, after in zip(path, path[1:]):
            if (before, after) not in ALLOWED_TRANSITIONS:
                bad.append(f"{c['customer_id']}: invalid transition {before} -> {after}")
        if path[-1] != c["status"]:
            bad.append(f"{c['customer_id']}: status {c['status']} but audit trail ends at {path[-1]}")
    return _result("lifecycle_transitions", "Customer status matches a valid audit-trail path", bad)


def check_review_closure(snap: Snapshot) -> CheckResult:
    bad = [r["review_id"] for r in snap.reviews if r["status"] == "CLOSED"
           and (r["closed_at"] is None or not r["closed_by"] or not (r["resolution"] or "").strip())]
    return _result("review_closure_integrity", "Closed reviews have closed_at, closed_by and a resolution", bad)


def check_duplicate_documents(snap: Snapshot) -> CheckResult:
    per_hash = defaultdict(set)
    for d in snap.documents:
        per_hash[d["file_hash"]].add(d["customer_id"])
    bad = [h[:12] for h, customers in per_hash.items() if len(customers) > 1]
    return _result("duplicate_documents", "No file hash is shared by documents of different customers", bad)


def check_derived_values(session, snap: Snapshot) -> CheckResult:
    latest = {}
    for document_id, result in session.execute(text("SELECT document_id, result FROM verification ORDER BY verification_id")):
        latest[document_id] = result
    bad = []
    for d in snap.documents:
        result = latest.get(d["document_id"])
        if result == "PENDING":
            expected = "SUBMITTED"
        elif result == "REJECTED":
            expected = "REJECTED"
        elif result == "VERIFIED":
            expected = "SUPERSEDED" if d["status"] == "SUPERSEDED" else (
                "EXPIRED" if d["expiry_date"] is not None and d["expiry_date"] < snap.as_of else "VERIFIED")
        else:
            expected = None
        if d["status"] != expected:
            bad.append(f"{d['document_id']}: stored {d['status']} but derived {expected}")
    for r in snap.reviews:
        if expected_status(r["due_date"], r["status"], snap.as_of) != r["status"]:
            bad.append(f"{r['review_id']}: past due but stored {r['status']}")
    ratings = defaultdict(int)
    for rating_id, customer_id, level, score, effective_to in session.execute(text(
            "SELECT rating_id, customer_id, level, score, effective_to FROM risk_rating")):
        if risk_level_for_score(score) != level:
            bad.append(f"{rating_id}: level {level} does not match score {score}")
        if effective_to is None:
            ratings[customer_id] += 1
    for c in snap.customers:
        if ratings.get(c["customer_id"], 0) != 1:
            bad.append(f"{c['customer_id']}: {ratings.get(c['customer_id'], 0)} current risk ratings")
    return _result("derived_value_reconciliation",
                   "Stored statuses and levels equal what the source records imply", bad)


BUCKETS = ["0", "1-25", "26-50", "51-75", "76-99", "100"]


def _bucket(percent: float) -> str:
    if percent <= 0:
        return "0"
    if percent >= 100:
        return "100"
    for label, high in (("1-25", 25), ("26-50", 50), ("51-75", 75), ("76-99", 99.99)):
        if percent <= high:
            return label
    return "76-99"


def completeness_distribution(snap: Snapshot) -> tuple[dict, list[str]]:
    """({customer status: {bucket: count}}, approved customers that are not 100% complete)."""
    dist: dict[str, Counter] = defaultdict(Counter)
    approved_incomplete = []
    for c in snap.customers:
        result = calculate_completeness(c["customer_type_id"], snap.current_risk[c["customer_id"]], snap.specs,
                                        snap.docs_by_customer.get(c["customer_id"], []), snap.as_of)
        dist[c["status"]][_bucket(result.percent)] += 1
        if c["status"] == "APPROVED" and result.percent < 100:
            approved_incomplete.append(f"{c['customer_id']}: {result.percent}%")
    return {s: {b: dist[s].get(b, 0) for b in BUCKETS} for s in sorted(dist)}, approved_incomplete


def check_completeness(snap: Snapshot) -> CheckResult:
    _, bad = completeness_distribution(snap)
    return _result("completeness_of_approved", "Every approved customer has 100% mandatory evidence", bad)


def check_expiry_alerts(snap: Snapshot) -> CheckResult:
    expected = {(a.document_id, a.alert_type, a.lead_days) for a in expected_expiry_alerts(
        snap.documents, snap.as_of, __import__("app.config", fromlist=["settings"]).settings.alert_lead_times)}
    stored = {(a["document_id"], a["alert_type"], a["lead_days"]) for a in snap.alerts
              if a["alert_type"] in ("EXPIRY_UPCOMING", "DOCUMENT_EXPIRED")}
    bad = [f"missing alert {k}" for k in sorted(expected - stored, key=str)] + \
          [f"unexpected alert {k}" for k in sorted(stored - expected, key=str)]
    return _result("expiry_alert_accuracy", "Expiry alerts exist exactly for documents that should have them", bad)


def run_all_checks(session, snap: Snapshot) -> list[CheckResult]:
    return [
        check_primary_keys(session),
        check_foreign_keys(session),
        check_enum_values(session),
        check_id_formats(session),
        check_date_ordering(session, snap.as_of),
        check_ownership_reconciliation(snap),
        check_lifecycle_transitions(session, snap),
        check_review_closure(snap),
        check_duplicate_documents(snap),
        check_derived_values(session, snap),
        check_completeness(snap),
        check_expiry_alerts(snap),
    ]
