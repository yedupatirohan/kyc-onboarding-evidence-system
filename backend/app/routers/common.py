"""Pagination and query helpers shared by every list endpoint."""
from math import ceil
from typing import Literal

from fastapi import Query

Order = Literal["asc", "desc"]
MAX_PAGE_SIZE = 200


class PageParams:
    """Dependency: ?page=1&page_size=50 (page >= 1, 1 <= page_size <= 200, else HTTP 422)."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page number"),
        page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE, description="rows per page (max 200)"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def make_page(items: list, total: int, params: PageParams) -> dict:
    pages = ceil(total / params.page_size) if total else 0
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size, "pages": pages}


def text_match(column, term: str):
    """Case-insensitive 'contains' that treats % and _ in the term literally."""
    from sqlalchemy import func
    return func.lower(column).contains(term.lower(), autoescape=True)


def day_start(d):
    from datetime import datetime, time
    return datetime.combine(d, time.min)


def next_day_start(d):
    from datetime import datetime, time, timedelta
    return datetime.combine(d + timedelta(days=1), time.min)
