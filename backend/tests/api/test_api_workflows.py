"""Reviews, alerts, exceptions and audit trail, checked against the rule layer and the detectors."""
from collections import Counter
from datetime import timedelta

import pytest

from app.config import settings
from app.services.anomaly_detection import (EXPECTED_DECISION, ISSUE_TYPES, REVIEW_CLOSED_NO_RESOLUTION, RULES,
                                            run_all_detectors)
from app.services.review_schedule import is_overdue
from app.services.snapshot import load_snapshot
from tests.api.conftest import SMALL, all_pages

RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ------------------------------------------------------------------ reviews
def test_reviews_total_and_status_partition(client):
    assert client.get("/api/reviews", params={"page_size": 1}).json()["total"] == SMALL["n_reviews"]
    parts = sum(client.get("/api/reviews", params={"status": s, "page_size": 1}).json()["total"]
                for s in ("SCHEDULED", "IN_PROGRESS", "CLOSED", "OVERDUE"))
    assert parts == SMALL["n_reviews"]
    assert client.get("/api/reviews", params={"status": "LATE"}).status_code == 422


def test_overdue_filter_matches_the_rule_service(client, db):
    snap = load_snapshot(db)
    expected = {r["review_id"] for r in snap.reviews if is_overdue(r["due_date"], r["status"], snap.as_of)}
    items = all_pages(client, "/api/reviews", overdue="true")
    assert {i["review_id"] for i in items} == expected
    assert all(i["days_overdue"] > 0 and i["status"] != "CLOSED" for i in items)
    rest = all_pages(client, "/api/reviews", overdue="false")
    assert len(rest) + len(items) == SMALL["n_reviews"] and all(i["days_overdue"] is None for i in rest)


def test_closed_without_resolution_matches_the_detector(client, db):
    expected = {f.entity_id for f in run_all_detectors(load_snapshot(db)) if f.issue_type == REVIEW_CLOSED_NO_RESOLUTION}
    assert expected
    items = all_pages(client, "/api/reviews", closed_without_resolution="true")
    assert {i["review_id"] for i in items} == expected


def test_review_filters_sort_and_validation(client):
    high = all_pages(client, "/api/reviews", risk_level="HIGH")
    assert high and all(i["risk_level"] == "HIGH" for i in high)
    dues = [i["due_date"] for i in all_pages(client, "/api/reviews", sort="due_date")]
    assert dues == sorted(dues)
    lo = settings.as_of_date
    inside = all_pages(client, "/api/reviews", due_from=lo.isoformat(), due_to=(lo + timedelta(days=60)).isoformat())
    assert all(lo.isoformat() <= i["due_date"] <= (lo + timedelta(days=60)).isoformat() for i in inside)
    assert client.get("/api/reviews", params={"due_from": "2026-13-45"}).status_code == 422
    assert client.get("/api/reviews", params={"due_from": "2026-12-01", "due_to": "2026-01-01"}).status_code == 422


def test_review_detail_and_404(client):
    first = client.get("/api/reviews", params={"page_size": 1}).json()["items"][0]
    body = client.get(f"/api/reviews/{first['review_id']}").json()
    assert body["review_id"] == first["review_id"] and body["customer_status"] and body["customer_name"]
    assert client.get("/api/reviews/REV-NOPE").status_code == 404


# ------------------------------------------------------------------ alerts
def test_alerts_total_and_filters(client):
    total = client.get("/api/alerts", params={"page_size": 1}).json()["total"]
    assert total == client.get("/api/health").json()["counts"]["alerts"]
    parts = sum(client.get("/api/alerts", params={"status": s, "page_size": 1}).json()["total"]
                for s in ("OPEN", "ACKNOWLEDGED", "RESOLVED"))
    assert parts == total
    items = all_pages(client, "/api/alerts", alert_type="EXPIRY_UPCOMING", severity="HIGH")
    assert items and all(i["alert_type"] == "EXPIRY_UPCOMING" and i["severity"] == "HIGH" for i in items)
    assert client.get("/api/alerts", params={"severity": "SCARY"}).status_code == 422
    assert client.get("/api/alerts", params={"alert_type": "NOPE"}).status_code == 422


def test_lead_days_filter(client):
    items = all_pages(client, "/api/alerts", lead_days=30)
    assert items and all(i["lead_days"] == 30 and i["alert_type"] == "EXPIRY_UPCOMING" for i in items)


def test_alert_sorting_by_severity_and_default_newest_first(client):
    ranks = [RANK[i["severity"]] for i in all_pages(client, "/api/alerts", sort="severity", order="desc")]
    assert ranks == sorted(ranks, reverse=True)
    dates = [i["created_at"] for i in all_pages(client, "/api/alerts")]
    assert dates == sorted(dates, reverse=True)


def test_alert_date_range_and_search(client):
    alert = client.get("/api/alerts", params={"page_size": 1}).json()["items"][0]
    day = alert["created_at"]
    same_day = all_pages(client, "/api/alerts", created_from=day, created_to=day)
    assert alert["alert_id"] in {i["alert_id"] for i in same_day}
    assert all(i["created_at"] == day for i in same_day)
    found = client.get("/api/alerts", params={"q": alert["alert_id"]}).json()
    assert [i["alert_id"] for i in found["items"]] == [alert["alert_id"]]
    assert client.get("/api/alerts", params={"created_from": "2026-12-01", "created_to": "2026-01-01"}).status_code == 422


def test_alert_detail_for_expiry_and_exception(client):
    expiry = client.get("/api/alerts", params={"alert_type": "EXPIRY_UPCOMING", "page_size": 1}).json()["items"][0]
    d = client.get(f"/api/alerts/{expiry['alert_id']}").json()
    assert d["is_exception"] is False and d["rule"] is None and d["document_id"]
    exc = client.get("/api/exceptions", params={"page_size": 1}).json()["items"][0]
    d = client.get(f"/api/alerts/{exc['alert_id']}").json()
    assert d["is_exception"] is True and d["rule"] == RULES[d["alert_type"]]
    assert client.get("/api/alerts/ALT-NOPE").status_code == 404


# ------------------------------------------------------------------ exceptions
def test_summary_counts_equal_live_detector_findings(client, db):
    """The alert table and the detectors must agree (the scan keeps them in sync)."""
    live = Counter(f.issue_type for f in run_all_detectors(load_snapshot(db)))
    summary = {s["issue_type"]: s for s in client.get("/api/exceptions/summary").json()}
    assert list(summary) == list(ISSUE_TYPES)
    for issue in ISSUE_TYPES:
        s = summary[issue]
        assert s["total"] == live[issue] >= 6, issue
        assert s["open"] + s["acknowledged"] + s["resolved"] == s["total"]
        assert s["rule"] == RULES[issue] and s["expected_decision"] == EXPECTED_DECISION[issue]


def test_exception_list_filters(client):
    total = client.get("/api/exceptions", params={"page_size": 1}).json()["total"]
    summary = client.get("/api/exceptions/summary").json()
    assert total == sum(s["total"] for s in summary)
    for issue in ISSUE_TYPES:
        items = all_pages(client, "/api/exceptions", issue_type=issue)
        assert items and all(i["alert_type"] == issue and i["expected_decision"] for i in items)
    crit = all_pages(client, "/api/exceptions", severity="CRITICAL")
    assert crit and all(i["alert_type"] == "APPROVED_MISSING_EVIDENCE" for i in crit)


def test_exceptions_reject_non_exception_types(client):
    assert client.get("/api/exceptions", params={"issue_type": "EXPIRY_UPCOMING"}).status_code == 422
    assert client.get("/api/exceptions", params={"issue_type": "NOPE"}).status_code == 422


# ------------------------------------------------------------------ audit
def test_audit_total_default_order_and_pagination(client):
    first = client.get("/api/audit-events", params={"page_size": 200}).json()
    assert first["total"] > 3000
    times = [e["occurred_at"] for e in first["items"]]
    assert times == sorted(times, reverse=True)
    assert client.get("/api/audit-events", params={"page_size": 201}).status_code == 422


def test_audit_facets_and_filters(client):
    facets = client.get("/api/audit-events/facets").json()
    assert {"customer", "document", "alert"} <= set(facets["entity_types"])
    assert "ALERT_RAISED" in facets["actions"] and "anomaly_detector" in facets["actors"]
    docs = client.get("/api/audit-events", params={"entity_type": "document", "page_size": 50}).json()
    assert docs["total"] > 0 and all(e["entity_type"] == "document" for e in docs["items"])
    one = docs["items"][0]
    same = all_pages(client, "/api/audit-events", entity_id=one["entity_id"])
    assert one["event_id"] in {e["event_id"] for e in same} and all(e["entity_id"] == one["entity_id"] for e in same)


def test_alert_raised_events_equal_exceptions_and_json_is_parsed(client):
    raised = all_pages(client, "/api/audit-events", action="ALERT_RAISED", actor="anomaly_detector")
    summary = client.get("/api/exceptions/summary").json()
    assert len(raised) == sum(s["total"] for s in summary)
    assert all(isinstance(e["new_value"], dict) and e["new_value"]["alert_type"] in ISSUE_TYPES for e in raised)


def test_audit_date_range_and_validation(client):
    day = client.get("/api/audit-events", params={"page_size": 1}).json()["items"][0]["occurred_at"][:10]
    items = all_pages(client, "/api/audit-events", occurred_from=day, occurred_to=day)
    assert items and all(e["occurred_at"][:10] == day for e in items)
    assert client.get("/api/audit-events", params={"occurred_from": "nope"}).status_code == 422
    assert client.get("/api/audit-events", params={"occurred_from": "2026-12-01", "occurred_to": "2026-01-01"}).status_code == 422


def test_audit_detail_404_and_read_only(client):
    ev = client.get("/api/audit-events", params={"page_size": 1}).json()["items"][0]
    assert client.get(f"/api/audit-events/{ev['event_id']}").json()["event_id"] == ev["event_id"]
    assert client.get("/api/audit-events/AUD-NOPE").status_code == 404
    assert client.delete(f"/api/audit-events/{ev['event_id']}").status_code == 405
    assert client.post("/api/alerts", json={}).status_code == 405
