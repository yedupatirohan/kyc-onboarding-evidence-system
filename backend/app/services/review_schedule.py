"""Review scheduling and overdue detection (pure functions)."""
from datetime import date

from app.config import settings
from app.services.dateutils import add_months


def review_frequency_months(risk_level: str) -> int:
    """Months between periodic reviews for a risk level (from settings)."""
    table = {
        "HIGH": settings.review_months_high,
        "MEDIUM": settings.review_months_medium,
        "LOW": settings.review_months_low,
    }
    if risk_level not in table:
        raise ValueError(f"Unknown risk level: {risk_level!r}")
    return table[risk_level]


def next_due_date(anchor: date, risk_level: str) -> date:
    return add_months(anchor, review_frequency_months(risk_level))


def current_cycle_due_date(onboarded_at: date, risk_level: str, as_of: date, look_back_days: int = 400) -> date:
    """First due date, stepping forward by the review frequency, that is not older than look_back_days."""
    from datetime import timedelta

    months = review_frequency_months(risk_level)
    due = add_months(onboarded_at, months)
    cutoff = as_of - timedelta(days=look_back_days)
    while due < cutoff:
        due = add_months(due, months)
    return due


def is_overdue(due_date: date, status: str, as_of: date) -> bool:
    """A review is overdue when its due date has passed and it is not closed."""
    return due_date < as_of and status != "CLOSED"


def expected_status(due_date: date, status: str, as_of: date) -> str:
    """The stored status that must hold given the dates (the reconciliation rule).

    Past due and not closed -> OVERDUE. Everything else keeps its stored status.
    """
    return "OVERDUE" if is_overdue(due_date, status, as_of) else status
