"""One call that feeds the dashboard screen."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_output_dir
from app.evidence import read_truth
from app.services.live_analysis import dashboard_summary, get_findings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), out_dir: Path = Depends(get_output_dir)) -> dict:
    from validation.evaluate import evaluate

    result = dashboard_summary(db)
    try:
        result["evaluation"] = evaluate(get_findings(db), read_truth(out_dir))["overall"]
    except FileNotFoundError:
        result["evaluation"] = None
    report = Path(out_dir) / "validation_report.json"
    result["reproducibility"] = None
    if report.exists():
        checks = json.loads(report.read_text(encoding="utf-8")).get("reproducibility_checksums", {})
        result["reproducibility"] = {"seed": json.loads(report.read_text(encoding="utf-8")).get("seed"),
                                     "baseline_database_sha256": checks.get("baseline_overall"),
                                     "final_database_sha256": checks.get("final_overall")}
    return result
