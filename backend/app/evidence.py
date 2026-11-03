"""Joins live detector findings with the labelled ground truth (API side only).

This lives OUTSIDE app/services on purpose: rule and detector code must never see the labels
(tests/test_detection_and_evaluation.py::test_detectors_never_read_ground_truth enforces it).
"""
from pathlib import Path


def read_truth(out_dir: Path) -> list[dict]:
    from generator.anomalies import read_ground_truth
    return read_ground_truth(Path(out_dir) / "ground_truth.csv")


def anomaly_rows(findings, truth: list[dict]) -> list[dict]:
    """Every labelled row plus any finding that has no label, each with its outcome."""
    by_key = {(f.issue_type, f.entity_id): f for f in findings}
    rows, seen = [], set()
    for t in truth:
        key = (t["issue_type"], t["entity_id"])
        seen.add(key)
        f = by_key.get(key)
        detected = f is not None
        if t["ground_truth"]:
            outcome = "TRUE_POSITIVE" if detected else "FALSE_NEGATIVE"
        else:
            outcome = "CONTROL_WRONGLY_FLAGGED" if detected else "CONTROL_CORRECTLY_IGNORED"
        rows.append({
            "ground_truth_id": t["ground_truth_id"], "issue_type": t["issue_type"], "entity_type": t["entity_type"],
            "entity_id": t["entity_id"], "customer_id": t["customer_id"], "label_kind": t["label_kind"],
            "ground_truth": t["ground_truth"], "detected": detected, "outcome": outcome,
            "severity": f.severity if f else None, "reason": f.reason if f else None,
            "rule_applied": t["rule_applied"], "injected_change": t["injected_change"],
            "expected_decision": t["expected_business_decision"],
        })
    for key, f in sorted(by_key.items()):
        if key not in seen:
            rows.append({
                "ground_truth_id": None, "issue_type": f.issue_type, "entity_type": f.entity_type,
                "entity_id": f.entity_id, "customer_id": f.customer_id, "label_kind": None, "ground_truth": None,
                "detected": True, "outcome": "UNLABELLED_FINDING", "severity": f.severity, "reason": f.reason,
                "rule_applied": None, "injected_change": None, "expected_decision": f.expected_decision,
            })
    rows.sort(key=lambda r: (r["issue_type"], r["entity_id"]))
    return rows
