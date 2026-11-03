"""Detector unit tests (positive AND near-miss cases) and the metrics maths."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services import anomaly_detection as ad
from validation.evaluate import evaluate

AS_OF = date(2026, 10, 22)
SERVICES_DIR = Path(ad.__file__).resolve().parent


def doc(doc_id, customer, status, expiry, file_hash="h"):
    return {"document_id": doc_id, "customer_id": customer, "status": status, "expiry_date": expiry, "file_hash": file_hash}


def link(link_id, customer, owner, pct, start=date(2026, 1, 1), end=None):
    return {"link_id": link_id, "customer_id": customer, "owner_id": owner, "ownership_pct": pct,
            "effective_from": start, "effective_to": end}


def test_expired_marked_valid_flags_only_the_real_problem():
    docs = [doc("A", "C1", "VERIFIED", date(2026, 10, 21)),     # expired yesterday, marked valid -> flag
            doc("B", "C1", "VERIFIED", date(2026, 10, 22)),     # expires today: still valid
            doc("C", "C1", "EXPIRED", date(2026, 10, 1)),       # correctly marked expired
            doc("D", "C1", "VERIFIED", None)]
    assert [f.entity_id for f in ad.detect_expired_marked_valid(docs, AS_OF)] == ["A"]


def test_ownership_over_100_uses_only_active_links():
    links = [link("1", "C1", "O1", Decimal("60")), link("2", "C1", "O2", Decimal("55")),             # 115 active -> flag
             link("3", "C2", "O3", Decimal("100"), end=date(2026, 3, 1)), link("4", "C2", "O4", Decimal("60")),
             link("5", "C2", "O5", Decimal("40")),                                                    # history + 100 -> fine
             link("6", "C3", "O6", Decimal("99.99"))]                                                 # under 100 -> not this rule
    found = ad.detect_ownership_over_100(links, AS_OF)
    assert [f.customer_id for f in found] == ["C1"]
    assert "115.00" in found[0].reason


def test_review_closed_without_resolution():
    reviews = [
        {"review_id": "R1", "customer_id": "C", "status": "CLOSED", "resolution": None, "closed_at": date(2026, 1, 1)},
        {"review_id": "R2", "customer_id": "C", "status": "CLOSED", "resolution": "  ", "closed_at": date(2026, 1, 1)},
        {"review_id": "R3", "customer_id": "C", "status": "CLOSED", "resolution": "ok", "closed_at": date(2026, 1, 1)},
        {"review_id": "R4", "customer_id": "C", "status": "OVERDUE", "resolution": None, "closed_at": None}]
    assert [f.entity_id for f in ad.detect_review_closed_no_resolution(reviews)] == ["R1", "R2"]


def test_duplicate_documents_unrelated_vs_related():
    docs = [doc("D1", "C1", "VERIFIED", None, "same"), doc("D2", "C2", "VERIFIED", None, "same"),     # unrelated -> flag both
            doc("D3", "C3", "VERIFIED", None, "dup2"), doc("D4", "C4", "VERIFIED", None, "dup2"),     # share an owner -> fine
            doc("D5", "C5", "VERIFIED", None, "mine"), doc("D6", "C5", "VERIFIED", None, "mine")]     # same customer -> fine
    links = [link("1", "C3", "O1", Decimal("100")), link("2", "C4", "O1", Decimal("100"))]
    assert [f.entity_id for f in ad.detect_duplicate_documents(docs, links)] == ["D1", "D2"]


def test_every_issue_type_has_severity_rule_and_decision():
    for issue in ad.ISSUE_TYPES:
        assert issue in ad.SEVERITY and issue in ad.RULES and issue in ad.EXPECTED_DECISION


def test_detectors_never_read_ground_truth():
    """No-leakage guard: rule code must not mention or import the labels."""
    for path in SERVICES_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "ground_truth" not in text, path.name
        assert "generator.anomalies" not in text, path.name


# ---------- evaluation maths ----------

class F:     # minimal finding stand-in
    def __init__(self, issue_type, entity_id):
        self.issue_type, self.entity_id = issue_type, entity_id


def truth(issue, entity, positive):
    return {"issue_type": issue, "entity_id": entity, "ground_truth": positive}


def test_precision_recall_and_control_handling():
    issue = ad.EXPIRED_MARKED_VALID
    gt = [truth(issue, "A", True), truth(issue, "B", True), truth(issue, "C", True), truth(issue, "N", False)]
    findings = [F(issue, "A"), F(issue, "B"), F(issue, "X"), F(issue, "N")]    # 2 TP, 2 FP (X and the control N), 1 FN (C)
    m = evaluate(findings, gt)["per_issue_type"][issue]
    assert (m["true_positives"], m["false_positives"], m["false_negatives"]) == (2, 2, 1)
    assert m["precision"] == 0.5 and m["recall"] == round(2 / 3, 4)
    assert m["controls_wrongly_flagged"] == 1
    assert m["missed"] == ["C"]


def test_perfect_detection_scores_one():
    issue = ad.OWNERSHIP_OVER_100
    result = evaluate([F(issue, "A")], [truth(issue, "A", True)])
    assert result["per_issue_type"][issue]["f1"] == 1.0
