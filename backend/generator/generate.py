"""The whole generator, end to end.   Run from the backend folder:

    python -m generator.generate

Stages (decision: valid baseline first, anomalies injected afterwards):
  1 reference data  2 customers  3 documents  4 owners  5 reviews  6 alerts  7 audit events
  8 verify the baseline is clean        9 inject labelled anomalies + write ground truth
  10 detect and raise exception alerts  11 evaluate against ground truth and write reports
"""
from datetime import date
from pathlib import Path

from sqlalchemy import insert, select

from app.config import PROJECT_ROOT, settings
from app.database import Base
from app.seed_reference import seed_reference_data
from app.services.anomaly_detection import run_all_detectors
from app.services.exceptions import run_exception_scan
from app.services.snapshot import load_snapshot
from generator.alerts import generate_alerts
from generator.anomalies import inject_anomalies, write_ground_truth
from generator.audit import generate_audit_events
from generator.customers import generate_customers, load_customers
from generator.db_utils import clear_generated_data
from generator.digest import compute_digests
from generator.documents import generate_documents, load_documents, read_customers
from generator.owners import generate_owners, load_owners, read_business_customers
from generator.reviews import generate_reviews
from validation.checks import run_all_checks
from validation.evaluate import evaluate
from validation.report import build_report, write_report


def _digests(session) -> dict:
    session.commit()
    return compute_digests(session.connection().connection.driver_connection)


def run_pipeline(session, n_customers=None, n_business=None, n_documents=None, n_reviews=None,
                 n_anomalies=60, n_controls=40, seed=None, out_dir: Path | None = None, log=print) -> dict:
    from app.models import AuditEvent, Alert, ReviewCase, RiskRating, Verification

    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "data" / "output"
    Base.metadata.create_all(session.get_bind())
    sizes = {"customers": n_customers or settings.n_customers, "business": n_business or settings.n_business,
             "documents": n_documents or settings.n_documents, "reviews": n_reviews or settings.n_reviews,
             "anomalies_per_scenario": n_anomalies, "controls_per_scenario": n_controls}

    seed_reference_data(session)
    clear_generated_data(session)

    customers = generate_customers(n_customers, n_business, seed)
    log(f"[1/10] customers       {load_customers(session, customers)}")
    cust_rows, risk = read_customers(session)
    from app.services.requirements import load_requirement_specs
    docs = generate_documents(cust_rows, risk, load_requirement_specs(session), n_documents, seed)
    log(f"[2/10] documents       {load_documents(session, docs)}")
    owners = generate_owners(read_business_customers(session), seed)
    log(f"[3/10] owners          {load_owners(session, owners)}")

    snap = load_snapshot(session)
    reviews = generate_reviews(snap.customers, snap.current_risk, n_reviews, seed)
    session.execute(insert(ReviewCase), reviews)
    log(f"[4/10] reviews         {len(reviews)}")
    alerts = generate_alerts(snap.documents, reviews, seed)
    session.execute(insert(Alert), alerts)
    log(f"[5/10] alerts          {len(alerts)}")

    ratings = [dict(r) for r in session.execute(select(
        RiskRating.rating_id, RiskRating.customer_id, RiskRating.level, RiskRating.score,
        RiskRating.effective_from, RiskRating.effective_to)).mappings()]
    verifications = [dict(r) for r in session.execute(select(
        Verification.document_id, Verification.result, Verification.verified_by, Verification.verified_at
    ).order_by(Verification.verification_id)).mappings()]
    audit = generate_audit_events(snap.customers, ratings, snap.documents, verifications, reviews, alerts, seed)
    session.execute(insert(AuditEvent), audit)
    session.commit()
    log(f"[6/10] audit events    {len(audit)}")

    # ---- the baseline must be clean before anything is corrupted ----------------------------
    clean_snap = load_snapshot(session)
    base_checks = run_all_checks(session, clean_snap)
    base_findings = run_all_detectors(clean_snap)
    baseline = {
        "checks_with_violations": sum(1 for c in base_checks if not c.passed),
        "anomaly_findings": len(base_findings),
        "clean": all(c.passed for c in base_checks) and not base_findings,
        "failing_checks": [c.name for c in base_checks if not c.passed],
    }
    log(f"[7/10] baseline clean  {baseline['clean']}")
    if not baseline["clean"]:
        raise RuntimeError(f"Baseline is not clean: {baseline}")
    baseline_digest = _digests(session)

    # ---- inject, detect, evaluate --------------------------------------------------------------
    truth = inject_anomalies(session, n_anomalies, n_controls, seed)
    files = write_ground_truth(truth, out_dir)
    positives = sum(1 for r in truth if r["ground_truth"])
    log(f"[8/10] ground truth    {positives} anomalies + {len(truth) - positives} controls -> {files['csv']}")

    scan = run_exception_scan(session)
    log(f"[9/10] exception scan  {len(scan['findings'])} findings, {scan['alerts_raised']} alerts raised")

    final_snap = load_snapshot(session)
    checks = run_all_checks(session, final_snap)
    evaluation = evaluate(scan["findings"], truth)
    final_digest = _digests(session)
    report = build_report(
        session, final_snap, baseline, checks, scan["findings"], evaluation,
        {"baseline_overall": baseline_digest["overall"], "baseline_tables": baseline_digest["tables"],
         "final_overall": final_digest["overall"], "final_tables": final_digest["tables"]},
        files, sizes)
    paths = write_report(report, out_dir)
    o = evaluation["overall"]
    log(f"[10/10] evaluation     precision={o['precision']} recall={o['recall']} f1={o['f1']}")
    return {"report": report, "paths": {**paths, **files}, "truth": truth}


def main() -> None:
    from app.database import SessionLocal
    with SessionLocal() as session:
        result = run_pipeline(session)
    print("Report:", result["paths"]["markdown"])
    print("Final OVERALL sha256:", result["report"]["reproducibility_checksums"]["final_overall"])


if __name__ == "__main__":
    main()
