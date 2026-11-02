"""Tests for the risk scoring rule (pure functions, no database)."""
import pytest

from app.services.risk import (
    BASE_SCORE_BY_TYPE, COUNTRY_POINTS, compute_risk_score, risk_level_for_score,
)


def test_score_is_sum_of_type_country_and_extra_points():
    assert compute_risk_score("INDIVIDUAL", "IN", 0) == 10
    assert compute_risk_score("COMPANY", "AE", 5) == 30 + 10 + 5
    assert compute_risk_score("TRUST", "PA", 3) == 40 + 25 + 3


def test_score_is_capped_at_100():
    assert compute_risk_score("TRUST", "NG", 55) == 100


@pytest.mark.parametrize("score,level", [
    (0, "LOW"), (34, "LOW"), (35, "MEDIUM"), (64, "MEDIUM"), (65, "HIGH"), (100, "HIGH"),
])
def test_level_boundaries(score, level):
    assert risk_level_for_score(score) == level


@pytest.mark.parametrize("bad", [-1, 101, 5.5, "40", None, True])
def test_level_rejects_invalid_scores(bad):
    with pytest.raises(ValueError):
        risk_level_for_score(bad)


def test_unknown_inputs_are_rejected():
    with pytest.raises(ValueError):
        compute_risk_score("ALIEN", "IN", 0)
    with pytest.raises(ValueError):
        compute_risk_score("INDIVIDUAL", "ZZ", 0)
    with pytest.raises(ValueError):
        compute_risk_score("INDIVIDUAL", "IN", -1)


def test_every_known_type_and_country_gives_a_valid_score():
    for t in BASE_SCORE_BY_TYPE:
        for c in COUNTRY_POINTS:
            assert 0 <= compute_risk_score(t, c, 0) <= 100
