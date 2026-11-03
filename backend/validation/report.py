"""Build and write the validation report (JSON for machines, Markdown for people).

The report contains no wall-clock timestamps, so two identical runs write identical files.
"""
import json
import platform
from collections import Counter
from importlib import metadata
from pathlib import Path

from sqlalchemy import text

from app.config import PROJECT_ROOT, settings
from app.database import Base
from app.services.expiry import lead_bucket
from app.services.snapshot import Snapshot
from validation.checks import CheckResult, completeness_distribution


def _versions() -> dict:
    out = {"python": platform.python_version()}
    for name in ("SQLAlchemy", "Faker", "pydantic", "fastapi"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def build_report(session, snap: Snapshot, baseline: dict, checks: list[CheckResult], findings,
                 evaluation: dict, digests: dict, ground_truth_files: dict, sizes: dict) -> dict:
    row_counts = {t.name: session.execute(text(f"SELECT COUNT(*) FROM {t.name}")).scalar() for t in Base.metadata.sorted_tables}
    distribution, _ = completeness_distribution(snap)

    leads = settings.alert_lead_times
    valid_docs = [d for d in snap.documents if d["status"] == "VERIFIED" and d["expiry_date"] and d["expiry_date"] >= snap.as_of]
    soon = Counter(lead_bucket((d["expiry_date"] - snap.as_of).days, leads) for d in valid_docs)
    expiry_stats = {
        "documents_by_status": dict(sorted(Counter(d["status"] for d in snap.documents).items())),
        "verified_and_unexpired": len(valid_docs),
        "expiring_within_lead_times": {f"{lead}_days": soon.get(lead, 0) for lead in sorted(leads)},
        "expired_but_marked_verified": sum(1 for d in snap.documents if d["status"] == "VERIFIED"
                                           and d["expiry_date"] and d["expiry_date"] < snap.as_of),
        "alerts_by_type": dict(sorted(Counter(a["alert_type"] for a in snap.alerts).items())),
        "alerts_by_status": dict(sorted(Counter(a["status"] for a in snap.alerts).items())),
    }
    review_stats = {
        "reviews_by_status": dict(sorted(Counter(r["status"] for r in snap.reviews).items())),
        "overdue_by_customer_risk": dict(sorted(Counter(
            snap.current_risk[r["customer_id"]] for r in snap.reviews if r["status"] == "OVERDUE").items())),
        "review_frequency_months": {"HIGH": settings.review_months_high, "MEDIUM": settings.review_months_medium,
                                    "LOW": settings.review_months_low},
    }
    return {
        "as_of_date": snap.as_of.isoformat(),
        "seed": settings.seed,
        "environment": _versions(),
        "dataset_sizes_requested": sizes,
        "dataset_row_counts": row_counts,
        "baseline": baseline,
        "validation_checks_after_injection": [
            {"name": c.name, "description": c.description, "violations": c.violations, "samples": c.samples}
            for c in checks],
        "anomaly_detection_summary": {
            "findings_by_issue_type": dict(sorted(Counter(f.issue_type for f in findings).items())),
            "findings_by_severity": dict(sorted(Counter(f.severity for f in findings).items())),
            "total_findings": len(findings),
        },
        "evaluation_against_ground_truth": evaluation,
        "completeness_distribution_by_customer_status": distribution,
        "expiry_statistics": expiry_stats,
        "review_statistics": review_stats,
        "reproducibility_checksums": {**digests, "ground_truth": {k: v for k, v in ground_truth_files.items() if k.endswith("sha256")}},
    }


def render_markdown(r: dict) -> str:
    lines = ["# Validation Report", "",
             f"As-of date: **{r['as_of_date']}** | Seed: **{r['seed']}**", "",
             "## Environment", ""]
    lines += [f"- {k}: {v}" for k, v in r["environment"].items()]
    lines += ["", "## Dataset row counts", "", "| Table | Rows |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in r["dataset_row_counts"].items()]
    b = r["baseline"]
    lines += ["", "## Clean baseline (before any anomaly is injected)", "",
              f"- Validation checks with violations: **{b['checks_with_violations']}**",
              f"- Anomaly findings: **{b['anomaly_findings']}**",
              f"- Baseline is clean: **{b['clean']}**", "",
              "## Validation checks after injection", "",
              "Violations here are the deliberately injected problems and show the checks work.", "",
              "| Check | Violations | Meaning |", "|---|---|---|"]
    lines += [f"| {c['name']} | {c['violations']} | {c['description']} |" for c in r["validation_checks_after_injection"]]
    lines += ["", "## Anomaly detection against ground truth", "",
              "| Issue type | Labelled | Detected | TP | FP | FN | Precision | Recall | Controls wrongly flagged |",
              "|---|---|---|---|---|---|---|---|---|"]
    for name, m in r["evaluation_against_ground_truth"]["per_issue_type"].items():
        lines.append(f"| {name} | {m['labelled_anomalies']} | {m['detected']} | {m['true_positives']} | "
                     f"{m['false_positives']} | {m['false_negatives']} | {m['precision']} | {m['recall']} | "
                     f"{m['controls_wrongly_flagged']} of {m['near_miss_controls']} |")
    o = r["evaluation_against_ground_truth"]["overall"]
    lines += ["", f"Overall: precision **{o['precision']}**, recall **{o['recall']}**, F1 **{o['f1']}**.", "",
              "## Completeness distribution (customers per bucket, by status)", "",
              "| Customer status | " + " | ".join(next(iter(r["completeness_distribution_by_customer_status"].values())).keys()) + " |",
              "|---|" + "---|" * 6]
    for status, buckets in r["completeness_distribution_by_customer_status"].items():
        lines.append(f"| {status} | " + " | ".join(str(v) for v in buckets.values()) + " |")
    lines += ["", "## Expiry statistics", "", "```json", json.dumps(r["expiry_statistics"], indent=2), "```", "",
              "## Review statistics", "", "```json", json.dumps(r["review_statistics"], indent=2), "```", "",
              "## Reproducibility checksums", "", f"- Baseline overall SHA-256: `{r['reproducibility_checksums']['baseline_overall']}`",
              f"- Final overall SHA-256: `{r['reproducibility_checksums']['final_overall']}`", ""]
    return "\n".join(lines)


def write_report(report: dict, out_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "data" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / "validation_report.json", out_dir / "validation_report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return {"json": str(json_path), "markdown": str(md_path)}
