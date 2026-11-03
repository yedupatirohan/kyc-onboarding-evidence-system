"""Detected anomalies compared with the labelled ground truth, and precision/recall."""
import hashlib
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_output_dir
from app.enums import AlertType
from app.routers.common import PageParams, make_page, text_match
from app.schemas.common import Page
from app.services.anomaly_detection import ISSUE_TYPES
from app.evidence import anomaly_rows, read_truth
from app.services.live_analysis import get_findings

router = APIRouter(tags=["anomalies"])

Outcome = Literal["TRUE_POSITIVE", "FALSE_NEGATIVE", "CONTROL_WRONGLY_FLAGGED", "CONTROL_CORRECTLY_IGNORED",
                  "UNLABELLED_FINDING"]
LabelKind = Literal["injected_anomaly", "near_miss_control"]


class AnomalyRow(BaseModel):
    ground_truth_id: str | None
    issue_type: str
    entity_type: str
    entity_id: str
    customer_id: str
    label_kind: str | None          # None = detector finding with no label at all
    ground_truth: bool | None       # True = injected anomaly, False = near-miss control
    detected: bool                  # did the live detectors flag it?
    outcome: str
    severity: str | None
    reason: str | None
    rule_applied: str | None
    injected_change: str | None
    expected_decision: str


def _truth(out_dir: Path) -> list[dict]:
    try:
        return read_truth(out_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="ground_truth.csv not found. Run: python -m generator.generate")


@router.get("/anomalies", response_model=Page[AnomalyRow])
def list_anomalies(
    params: PageParams = Depends(),
    issue_type: AlertType | None = None,
    outcome: Outcome | None = None,
    label_kind: LabelKind | None = None,
    detected: bool | None = None,
    customer_id: str | None = Query(None, max_length=10),
    q: str | None = Query(None, min_length=1, max_length=100, description="entity id contains"),
    db: Session = Depends(get_db),
    out_dir: Path = Depends(get_output_dir),
):
    if issue_type and issue_type.value not in ISSUE_TYPES:
        raise HTTPException(status_code=422, detail=f"issue_type must be one of {', '.join(ISSUE_TYPES)}")
    rows = anomaly_rows(get_findings(db), _truth(out_dir))
    if issue_type:
        rows = [r for r in rows if r["issue_type"] == issue_type.value]
    if outcome:
        rows = [r for r in rows if r["outcome"] == outcome]
    if label_kind:
        rows = [r for r in rows if r["label_kind"] == label_kind]
    if detected is not None:
        rows = [r for r in rows if r["detected"] == detected]
    if customer_id:
        rows = [r for r in rows if r["customer_id"] == customer_id]
    if q:
        rows = [r for r in rows if q.lower() in r["entity_id"].lower()]
    return make_page(rows[params.offset:params.offset + params.page_size], len(rows), params)


@router.get("/evaluation")
def evaluation(db: Session = Depends(get_db), out_dir: Path = Depends(get_output_dir)) -> dict:
    """Live detectors vs ground truth. The detectors never read the labels; only this endpoint joins them."""
    from validation.evaluate import evaluate

    truth = _truth(out_dir)
    path = Path(out_dir) / "ground_truth.csv"
    positives = sum(1 for r in truth if r["ground_truth"])
    return {
        "as_of_date": settings.as_of_date,
        "source": {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "rows": len(truth), "injected_anomalies": positives, "near_miss_controls": len(truth) - positives},
        **evaluate(get_findings(db), truth),
    }
