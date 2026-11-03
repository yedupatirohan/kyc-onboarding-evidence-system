"""End-to-end tests of the whole generator on a small dataset (fast), in memory."""
import csv
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database import Base
from app.services.exceptions import run_exception_scan
from generator.generate import run_pipeline

SMALL = dict(n_customers=900, n_business=120, n_documents=2700, n_reviews=250, n_anomalies=6, n_controls=4)


def new_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    session = new_session()
    result = run_pipeline(session, out_dir=out, log=lambda *_: None, **SMALL)
    yield session, result, out
    session.close()


def test_baseline_is_clean_before_injection(run):
    assert run[1]["report"]["baseline"] == {
        "checks_with_violations": 0, "anomaly_findings": 0, "clean": True, "failing_checks": []}


def test_requested_sizes_are_produced(run):
    counts = run[1]["report"]["dataset_row_counts"]
    assert counts["customer"] == 900 and counts["business_profile"] == 120
    assert counts["document"] == 2700 and counts["review_case"] == 250
    assert counts["audit_event"] > 3000


def test_every_scenario_is_detected_without_false_alarms(run):
    evaluation = run[1]["report"]["evaluation_against_ground_truth"]
    for issue, m in evaluation["per_issue_type"].items():
        assert m["labelled_anomalies"] >= 6, issue
        assert (m["false_positives"], m["false_negatives"], m["controls_wrongly_flagged"]) == (0, 0, 0), issue
    assert evaluation["overall"]["precision"] == 1.0 and evaluation["overall"]["recall"] == 1.0


def test_injection_changed_only_the_intended_tables(run):
    base, final = run[1]["report"]["reproducibility_checksums"]["baseline_tables"], run[1]["report"]["reproducibility_checksums"]["final_tables"]
    changed = {t for t in final if final[t]["sha256"] != base[t]["sha256"]}
    assert changed == {"document", "customer", "ownership_link", "review_case", "alert", "audit_event"}
    for untouched in ("verification", "risk_rating", "beneficial_owner", "business_profile", "document_requirement_link"):
        assert final[untouched] == base[untouched], untouched


def test_ground_truth_files_exist_and_agree(run):
    _, result, out = run
    with open(out / "ground_truth.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    data = json.loads((out / "ground_truth.json").read_text(encoding="utf-8"))
    assert len(rows) == len(data) == len(result["truth"])
    assert {r["issue_type"] for r in rows} == {
        "EXPIRED_MARKED_VALID", "APPROVED_MISSING_EVIDENCE", "OWNERSHIP_OVER_100",
        "REVIEW_CLOSED_NO_RESOLUTION", "DUPLICATE_DOCUMENT"}
    assert {r["label_kind"] for r in rows} == {"injected_anomaly", "near_miss_control"}
    assert len({r["ground_truth_id"] for r in rows}) == len(rows)


def test_operational_tables_hold_no_labels(run):
    session = run[0]
    from sqlalchemy import inspect
    for table in inspect(session.get_bind()).get_table_names():
        for column in inspect(session.get_bind()).get_columns(table):
            assert "ground_truth" not in column["name"] and column["name"] != "issue_type", (table, column["name"])


def test_exception_alerts_trace_back_to_entities(run):
    from sqlalchemy import text
    session = run[0]
    rows = session.execute(text(
        "SELECT alert_type, customer_id, document_id, message FROM alert "
        "WHERE alert_type IN ('EXPIRED_MARKED_VALID','APPROVED_MISSING_EVIDENCE','OWNERSHIP_OVER_100',"
        "'REVIEW_CLOSED_NO_RESOLUTION','DUPLICATE_DOCUMENT')")).all()
    assert len(rows) > 0
    for alert_type, customer_id, document_id, message in rows:
        assert customer_id and message
        if alert_type in ("EXPIRED_MARKED_VALID", "DUPLICATE_DOCUMENT"):
            assert document_id


def test_rescan_is_idempotent_and_auto_resolves_fixed_data(run):
    from sqlalchemy import text
    session = run[0]
    again = run_exception_scan(session)
    assert again["alerts_raised"] == 0 and again["alerts_auto_resolved"] == 0
    # fix one problem: give a closed review a resolution again
    review_id = session.execute(text("SELECT entity_id FROM audit_event WHERE 1=0")).first()  # no-op, keeps style simple
    row = session.execute(text(
        "SELECT review_id FROM review_case WHERE status='CLOSED' AND resolution IS NULL LIMIT 1")).first()
    session.execute(text("UPDATE review_case SET resolution='Fixed after escalation' WHERE review_id=:r"), {"r": row[0]})
    session.commit()
    third = run_exception_scan(session)
    assert third["alerts_auto_resolved"] == 1


def test_the_whole_pipeline_is_reproducible(tmp_path):
    fingerprints = []
    for number in (1, 2):
        session = new_session()
        result = run_pipeline(session, out_dir=tmp_path / f"run{number}", log=lambda *_: None, **SMALL)
        checks = result["report"]["reproducibility_checksums"]
        fingerprints.append((checks["baseline_overall"], checks["final_overall"], checks["ground_truth"],
                             (tmp_path / f"run{number}" / "validation_report.json").read_text(encoding="utf-8")))
        session.close()
    assert fingerprints[0] == fingerprints[1]
