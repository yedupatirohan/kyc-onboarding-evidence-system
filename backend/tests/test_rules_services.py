"""Unit tests for the pure rule modules: expiry, review schedule, completeness."""
from datetime import date

import pytest

from app.services.completeness import calculate_completeness, document_state
from app.services.expiry import expected_expiry_alerts, lead_bucket
from app.services.requirements import RequirementSpec
from app.services.review_schedule import (current_cycle_due_date, expected_status, is_overdue,
                                          next_due_date, review_frequency_months)

AS_OF = date(2026, 10, 22)


# ---------- expiry ----------

@pytest.mark.parametrize("days,expected", [(0, 30), (30, 30), (31, 60), (60, 60), (61, 90), (90, 90), (91, None), (-1, None)])
def test_lead_bucket_boundaries(days, expected):
    assert lead_bucket(days, [90, 60, 30]) == expected


def test_lead_times_are_configurable():
    assert lead_bucket(10, [14, 7]) == 14
    assert lead_bucket(5, [14, 7]) == 7
    assert lead_bucket(20, [14, 7]) is None


def doc(doc_id, status, expiry, customer="CUS-000001"):
    return {"document_id": doc_id, "customer_id": customer, "status": status, "expiry_date": expiry}


def test_expected_alerts_follow_the_rules():
    docs = [
        doc("D1", "VERIFIED", date(2026, 11, 5)),     # 14 days -> 30-day alert
        doc("D2", "VERIFIED", date(2026, 12, 25)),    # 64 days -> 90-day alert
        doc("D3", "VERIFIED", date(2027, 6, 1)),      # far away -> none
        doc("D4", "EXPIRED", date(2026, 9, 1)),       # expired alert
        doc("D5", "SUBMITTED", date(2026, 11, 1)),    # pending docs never alert
        doc("D6", "VERIFIED", None),                  # no expiry -> none
        doc("D7", "VERIFIED", date(2026, 10, 1)),     # marked valid but expired -> expired alert
    ]
    got = {(a.document_id, a.alert_type, a.lead_days) for a in expected_expiry_alerts(docs, AS_OF, [90, 60, 30])}
    assert got == {("D1", "EXPIRY_UPCOMING", 30), ("D2", "EXPIRY_UPCOMING", 90),
                   ("D4", "DOCUMENT_EXPIRED", None), ("D7", "DOCUMENT_EXPIRED", None)}


# ---------- review schedule ----------

def test_review_frequency_depends_on_risk():
    assert (review_frequency_months("HIGH"), review_frequency_months("MEDIUM"), review_frequency_months("LOW")) == (6, 12, 24)
    with pytest.raises(ValueError):
        review_frequency_months("EXTREME")


def test_next_due_date_and_cycle():
    assert next_due_date(date(2026, 1, 31), "HIGH") == date(2026, 7, 31)
    due = current_cycle_due_date(date(2024, 1, 1), "HIGH", AS_OF)
    assert due == date(2025, 11, 1) or due >= date(2025, 9, 18)     # not older than 400 days
    assert (AS_OF - due).days <= 400


def test_overdue_rule():
    assert is_overdue(date(2026, 10, 21), "SCHEDULED", AS_OF)
    assert not is_overdue(date(2026, 10, 22), "SCHEDULED", AS_OF)       # due today is not overdue
    assert not is_overdue(date(2026, 1, 1), "CLOSED", AS_OF)
    assert expected_status(date(2026, 10, 1), "IN_PROGRESS", AS_OF) == "OVERDUE"
    assert expected_status(date(2026, 12, 1), "SCHEDULED", AS_OF) == "SCHEDULED"


# ---------- completeness (the worked example from Phase 1) ----------

def spec(rid, name, min_risk="LOW", mandatory=True, types=("INDIVIDUAL",)):
    return RequirementSpec(rid, name, mandatory, min_risk, 12, date(2026, 1, 1), None, frozenset(types))


SPECS = [spec("R1", "Passport"), spec("R2", "Proof of Address"), spec("R3", "Source of Funds", "HIGH"),
         spec("R4", "Selfie"), spec("R5", "Income proof", "LOW", mandatory=False)]


def d(doc_id, status, expiry, reqs):
    return {"document_id": doc_id, "status": status, "expiry_date": expiry, "requirement_ids": reqs}


def test_phase1_example_gives_25_percent():
    docs = [d("A", "VERIFIED", date(2030, 1, 1), ("R1",)),
            d("B", "VERIFIED", date(2026, 9, 1), ("R2",)),        # verified but expired
            d("C", "SUBMITTED", None, ("R3",))]                    # pending
    result = calculate_completeness("INDIVIDUAL", "HIGH", SPECS, docs, AS_OF)
    assert (result.required, result.satisfied, result.percent) == (4, 1, 25.0)
    reasons = {m["name"]: m["reason"] for m in result.missing}
    assert reasons == {"Proof of Address": "Document expired on 2026-09-01",
                       "Source of Funds": "Document pending verification",
                       "Selfie": "No document submitted"}
    assert result.label == "INCOMPLETE"


def test_complete_and_optional_does_not_count():
    docs = [d("A", "VERIFIED", None, ("R1",)), d("B", "VERIFIED", date(2027, 1, 1), ("R2",)),
            d("C", "VERIFIED", None, ("R4",))]
    result = calculate_completeness("INDIVIDUAL", "LOW", SPECS, docs, AS_OF)
    assert (result.percent, result.label, result.missing) == (100.0, "COMPLETE", [])


def test_no_requirements_means_100_percent_not_division_by_zero():
    assert calculate_completeness("ALIEN", "LOW", SPECS, [], AS_OF).percent == 100.0


def test_one_document_can_satisfy_two_requirements():
    docs = [d("A", "VERIFIED", date(2027, 1, 1), ("R1", "R2")), d("B", "VERIFIED", None, ("R4",))]
    assert calculate_completeness("INDIVIDUAL", "LOW", SPECS, docs, AS_OF).percent == 100.0


def test_superseded_documents_are_ignored_and_best_document_wins():
    docs = [d("OLD", "SUPERSEDED", date(2026, 1, 1), ("R1",)), d("BAD", "REJECTED", None, ("R1",)),
            d("NEW", "VERIFIED", date(2027, 1, 1), ("R1",))]
    assert document_state(docs[0], AS_OF) == "IGNORED"
    result = calculate_completeness("INDIVIDUAL", "LOW", SPECS[:1], docs, AS_OF)
    assert result.percent == 100.0


def test_all_missing_items_pending_gives_pending_verification_label():
    docs = [d("A", "SUBMITTED", None, ("R1",))]
    assert calculate_completeness("INDIVIDUAL", "LOW", SPECS[:1], docs, AS_OF).label == "PENDING_VERIFICATION"
