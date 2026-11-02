"""Risk scoring rule: a pure function of documented inputs (no database, no randomness)."""

# Illustrative points by customer type (assumption, not a regulatory table).
BASE_SCORE_BY_TYPE = {
    "INDIVIDUAL": 10,
    "SOLE_PROPRIETOR": 20,
    "COMPANY": 30,
    "TRUST": 40,
}

# Illustrative jurisdiction points (assumption; NOT taken from any official list).
COUNTRY_POINTS = {
    "IN": 0, "GB": 0, "US": 0, "DE": 0, "AU": 0, "SG": 0,
    "AE": 10,
    "PA": 25, "NG": 25, "MM": 25,
}

# Level thresholds on the 0-100 score.
LOW_MAX = 34      # 0..34   -> LOW
MEDIUM_MAX = 64   # 35..64  -> MEDIUM, 65..100 -> HIGH


def compute_risk_score(customer_type_id: str, country_code: str, extra_points: int) -> int:
    """score = type points + country points + extra points, limited to 0..100.

    extra_points stands for factors we do not model in detail
    (for example politically exposed person flag, adverse media, product risk).
    """
    if customer_type_id not in BASE_SCORE_BY_TYPE:
        raise ValueError(f"Unknown customer type: {customer_type_id!r}")
    if country_code not in COUNTRY_POINTS:
        raise ValueError(f"Unknown country code: {country_code!r}")
    if isinstance(extra_points, bool) or not isinstance(extra_points, int) or extra_points < 0:
        raise ValueError(f"extra_points must be a non-negative integer, got {extra_points!r}")
    raw = BASE_SCORE_BY_TYPE[customer_type_id] + COUNTRY_POINTS[country_code] + extra_points
    return max(0, min(100, raw))


def risk_level_for_score(score: int) -> str:
    """Map a 0..100 score to LOW / MEDIUM / HIGH."""
    if isinstance(score, bool) or not isinstance(score, int) or not (0 <= score <= 100):
        raise ValueError(f"score must be an integer from 0 to 100, got {score!r}")
    if score <= LOW_MAX:
        return "LOW"
    if score <= MEDIUM_MAX:
        return "MEDIUM"
    return "HIGH"
