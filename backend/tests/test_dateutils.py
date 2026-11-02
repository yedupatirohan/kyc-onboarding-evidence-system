"""Tests for add_months."""
from datetime import date

import pytest

from app.services.dateutils import add_months


def test_simple_forward_and_backward():
    assert add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)
    assert add_months(date(2026, 3, 15), -2) == date(2026, 1, 15)


def test_year_rollover():
    assert add_months(date(2026, 11, 10), 3) == date(2027, 2, 10)
    assert add_months(date(2026, 1, 10), -2) == date(2025, 11, 10)


def test_short_month_clamps_to_last_day():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)


def test_leap_day_handling():
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_twelve_months_is_one_year():
    assert add_months(date(2026, 10, 22), 12) == date(2027, 10, 22)
    assert add_months(date(2026, 10, 22), 120) == date(2036, 10, 22)


def test_rejects_non_integer_months():
    with pytest.raises(ValueError):
        add_months(date(2026, 1, 1), 1.5)
    with pytest.raises(ValueError):
        add_months(date(2026, 1, 1), True)
