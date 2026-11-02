"""Small date helpers shared by the generator and the business rules."""
import calendar
from datetime import date


def add_months(start: date, months: int) -> date:
    """Move a date by whole months, keeping the day where possible.

    If the target month is shorter, the day is clamped to its last day:
    add_months(2026-01-31, 1) -> 2026-02-28. Negative months go backwards.
    """
    if isinstance(months, bool) or not isinstance(months, int):
        raise ValueError(f"months must be an integer, got {months!r}")
    month_index = start.year * 12 + (start.month - 1) + months
    year, month = divmod(month_index, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day))
