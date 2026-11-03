"""Anomalies vs ground truth, evaluation, validation and the dashboard summary."""
import csv
import json

import pytest

from app.deps import get_output_dir
from app.main import app
from app.services.anomaly_detection import ISSUE_TYPES
from tests.api.conftest import SMALL, all_pages


def truth_rows(out_dir):
    with open(out_dir / "ground_truth.csv", newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


# ------------------------------------------------------------------ anomalies
def test_every_label_appears_once_and_nothing_is_unlabelled(client, out_dir):
    rows = all_pages(client, "/api/anomalies")
    labels = truth_rows(out_dir)
    assert len(rows) == len(labels) and len(rows) >= 50
    assert {r["ground_truth_id"] for r in rows} == {t["ground_truth_id"] for t in labels}
    assert not [r for r in rows if r["outcome"] == "UNLABELLED_FINDING"]


def test_detector_outcomes_are_perfect_on_this_dataset(client):
    outcomes = {r["outcome"] for r in all_pages(client, "/api/anomalies")}
    assert outcomes == {"TRUE_POSITIVE", "CONTROL_CORRECTLY_IGNORED"}        # no misses, no false alarms


def test_anomaly_filters(client, out_dir):
    labels = truth_rows(out_dir)
    positives = sum(1 for t in labels if t["ground_truth"] == "True")
    tp = client.get("/api/anomalies", params={"outcome": "TRUE_POSITIVE", "page_size": 1}).json()["total"]
    assert tp == positives
    ctrl = all_pages(client, "/api/anomalies", label_kind="near_miss_control")
    assert ctrl and all(r["detected"] is False and r["ground_truth"] is False for r in ctrl)
    for issue in ISSUE_TYPES:
        items = all_pages(client, "/api/anomalies", issue_type=issue)
        assert items and {r["issue_type"] for r in items} == {issue}
    undetected = client.get("/api/anomalies", params={"detected": "false", "page_size": 1}).json()["total"]
    assert undetected == len(labels) - positives
    assert client.get("/api/anomalies", params={"issue_type": "EXPIRY_UPCOMING"}).status_code == 422
    assert client.get("/api/anomalies", params={"outcome": "MAYBE"}).status_code == 422


def test_true_positive_rows_carry_reason_rule_and_decision(client):
    row = client.get("/api/anomalies", params={"outcome": "TRUE_POSITIVE", "page_size": 1}).json()["items"][0]
    assert row["reason"] and row["rule_applied"] and row["injected_change"] and row["expected_decision"]
    assert row["severity"] in {"MEDIUM", "HIGH", "CRITICAL"}


def test_anomaly_search_and_pagination(client):
    first = client.get("/api/anomalies", params={"page_size": 1}).json()["items"][0]
    found = client.get("/api/anomalies", params={"q": first["entity_id"].lower()}).json()
    assert first["entity_id"] in {r["entity_id"] for r in found["items"]}
    assert client.get("/api/anomalies", params={"page_size": 500}).status_code == 422


# ------------------------------------------------------------------ evaluation
def test_evaluation_is_perfect_and_matches_the_stored_report(client, out_dir):
    live = client.get("/api/evaluation").json()
    stored = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert live["overall"] == stored["evaluation_against_ground_truth"]["overall"]
    assert live["overall"]["precision"] == 1.0 and live["overall"]["recall"] == 1.0
    assert set(live["per_issue_type"]) == set(ISSUE_TYPES)
    for issue, m in live["per_issue_type"].items():
        assert (m["false_positives"], m["false_negatives"], m["controls_wrongly_flagged"]) == (0, 0, 0), issue
    assert live["source"]["rows"] == len(truth_rows(out_dir)) and len(live["source"]["sha256"]) == 64


# ------------------------------------------------------------------ validation
def test_live_checks_equal_the_stored_report(client, out_dir):
    live = client.get("/api/validation").json()
    stored = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
    expected = {c["name"]: c["violations"] for c in stored["validation_checks_after_injection"]}
    assert live["total"] == 12 and live["passing"] + live["failing"] == 12
    assert {c["name"]: c["violations"] for c in live["checks"]} == expected
    assert all(c["passed"] == (c["violations"] == 0) for c in live["checks"])


def test_stored_report_proves_a_clean_baseline(client):
    report = client.get("/api/validation/report").json()
    assert report["baseline"]["clean"] is True and report["baseline"]["checks_with_violations"] == 0
    assert report["seed"] == 20261022 and len(report["reproducibility_checksums"]["final_overall"]) == 64


def test_row_counts_cover_all_14_tables_and_match_the_report(client, out_dir):
    body = client.get("/api/validation/row-counts").json()
    stored = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert body["tables"] == 14 and body["counts"] == stored["dataset_row_counts"]
    assert body["counts"]["customer"] == SMALL["n_customers"]


# ------------------------------------------------------------------ dashboard
def test_dashboard_totals_agree_with_the_list_endpoints(client):
    d = client.get("/api/dashboard/summary").json()
    total = lambda path, **p: client.get(path, params={**p, "page_size": 1}).json()["total"]
    assert d["customers"]["total"] == total("/api/customers") == SMALL["n_customers"]
    assert sum(d["customers"]["by_status"].values()) == d["customers"]["total"]
    assert sum(d["customers"]["by_risk_level"].values()) == d["customers"]["total"]
    assert d["documents"]["total"] == total("/api/documents")
    assert d["alerts"]["total"] == total("/api/alerts") and d["alerts"]["open"] == total("/api/alerts", status="OPEN")
    assert d["reviews"]["overdue"] == total("/api/reviews", overdue="true")
    assert d["exceptions"]["total"] == total("/api/exceptions")


def test_dashboard_completeness_equals_the_customer_filter(client):
    d = client.get("/api/dashboard/summary").json()["completeness"]
    for label in ("COMPLETE", "INCOMPLETE", "PENDING_VERIFICATION"):
        n = client.get("/api/customers", params={"completeness": label, "page_size": 1}).json()["total"]
        assert d["by_label"].get(label, 0) == n, label
    live = {c["name"]: c["violations"] for c in client.get("/api/validation").json()["checks"]}
    assert d["approved_incomplete"] == live["completeness_of_approved"]      # same rule, two routes


def test_dashboard_document_buckets_agree_with_state_filter(client):
    d = client.get("/api/dashboard/summary").json()["documents"]
    for state, n in d["by_state"].items():
        assert client.get("/api/documents", params={"state": state, "page_size": 1}).json()["total"] == n
    for days, n in d["verified_expiring_within_days"].items():
        got = client.get("/api/documents", params={"expiring_within_days": int(days), "page_size": 1}).json()["total"]
        assert got == n


def test_dashboard_embeds_evaluation_and_reproducibility(client):
    d = client.get("/api/dashboard/summary").json()
    assert d["evaluation"]["precision"] == 1.0 and d["evaluation"]["recall"] == 1.0
    assert d["reproducibility"]["seed"] == 20261022 and len(d["reproducibility"]["final_database_sha256"]) == 64


# ------------------------------------------------------------------ missing evidence files
def test_missing_ground_truth_gives_404_not_a_crash(client, tmp_path):
    original = app.dependency_overrides[get_output_dir]
    app.dependency_overrides[get_output_dir] = lambda: tmp_path                    # an empty folder
    try:
        assert client.get("/api/anomalies").status_code == 404
        assert client.get("/api/evaluation").status_code == 404
        assert client.get("/api/validation/report").status_code == 404
        d = client.get("/api/dashboard/summary").json()
        assert d["evaluation"] is None and d["reproducibility"] is None and d["customers"]["total"] == 900
    finally:
        app.dependency_overrides[get_output_dir] = original


def test_evidence_endpoints_are_read_only(client):
    assert client.post("/api/validation", json={}).status_code == 405
    assert client.delete("/api/anomalies").status_code == 405
