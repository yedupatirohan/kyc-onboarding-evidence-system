"""Compare detector output with ground truth (the only place the two ever meet)."""
from collections import defaultdict

from app.services.anomaly_detection import ISSUE_TYPES


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def evaluate(findings, ground_truth_rows: list[dict]) -> dict:
    predicted = defaultdict(set)
    for f in findings:
        predicted[f.issue_type].add(f.entity_id)
    positives, controls = defaultdict(set), defaultdict(set)
    for r in ground_truth_rows:
        (positives if r["ground_truth"] else controls)[r["issue_type"]].add(r["entity_id"])

    per_type, total_tp, total_fp, total_fn = {}, 0, 0, 0
    for issue in ISSUE_TYPES:
        tp = predicted[issue] & positives[issue]
        fp = predicted[issue] - positives[issue]
        fn = positives[issue] - predicted[issue]
        control_fp = predicted[issue] & controls[issue]
        precision, recall = _ratio(len(tp), len(tp) + len(fp)), _ratio(len(tp), len(tp) + len(fn))
        per_type[issue] = {
            "labelled_anomalies": len(positives[issue]), "detected": len(predicted[issue]),
            "true_positives": len(tp), "false_positives": len(fp), "false_negatives": len(fn),
            "near_miss_controls": len(controls[issue]), "controls_wrongly_flagged": len(control_fp),
            "precision": precision, "recall": recall,
            "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
            "missed": sorted(fn)[:5], "false_alarms": sorted(fp)[:5],
        }
        total_tp, total_fp, total_fn = total_tp + len(tp), total_fp + len(fp), total_fn + len(fn)
    precision, recall = _ratio(total_tp, total_tp + total_fp), _ratio(total_tp, total_tp + total_fn)
    return {
        "per_issue_type": per_type,
        "overall": {"true_positives": total_tp, "false_positives": total_fp, "false_negatives": total_fn,
                    "precision": precision, "recall": recall,
                    "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0},
    }
