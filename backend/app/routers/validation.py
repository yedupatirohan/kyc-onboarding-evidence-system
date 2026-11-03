"""Data-quality evidence: live validation checks, the stored report, and per-table row counts."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, get_db
from app.deps import get_output_dir
from app.services.live_analysis import get_checks

router = APIRouter(prefix="/validation", tags=["validation"])


@router.get("")
def run_checks(db: Session = Depends(get_db)) -> dict:
    checks = get_checks(db)
    return {
        "as_of_date": settings.as_of_date,
        "note": "The dataset contains deliberately injected anomalies, so some checks are EXPECTED to report "
                "violations. The clean-baseline proof (0 violations before injection) is in /validation/report.",
        "total": len(checks), "passing": sum(1 for c in checks if c.passed),
        "failing": sum(1 for c in checks if not c.passed),
        "checks": [{"name": c.name, "description": c.description, "violations": c.violations,
                    "passed": c.passed, "samples": c.samples} for c in checks],
    }


@router.get("/report")
def stored_report(out_dir: Path = Depends(get_output_dir)) -> dict:
    """The validation_report.json written by the pipeline (baseline proof, checksums, environment)."""
    path = Path(out_dir) / "validation_report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="validation_report.json not found. Run: python -m generator.generate")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/row-counts")
def row_counts(db: Session = Depends(get_db)) -> dict:
    counts = {t.name: db.execute(text(f"SELECT COUNT(*) FROM {t.name}")).scalar() for t in Base.metadata.sorted_tables}
    return {"tables": len(counts), "counts": counts}
