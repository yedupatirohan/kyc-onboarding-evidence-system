"""Shared response shapes."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int          # rows matching the filters, across all pages
    page: int           # 1-based
    page_size: int
    pages: int          # 0 when there are no rows
