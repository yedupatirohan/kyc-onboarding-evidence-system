"""Helpers shared by the generator steps."""
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.database import Base

# Master data is seeded separately and must survive a regeneration.
REFERENCE_TABLES = {"customer_type", "kyc_requirement", "customer_type_requirement"}


def clear_generated_data(session: Session) -> dict[str, int]:
    """Delete every generated row (everything except master data).

    Tables are emptied children-first, because a parent row cannot be deleted
    while child rows still point at it. Returns rows deleted per table.
    """
    deleted: dict[str, int] = {}
    for table in reversed(Base.metadata.sorted_tables):  # sorted_tables is parents-first
        if table.name in REFERENCE_TABLES:
            continue
        result = session.execute(delete(table))
        deleted[table.name] = result.rowcount
    session.commit()
    return deleted


def clear_tables(session: Session, names: list[str]) -> dict[str, int]:
    """Delete rows from only the named tables, children first.

    Used by a generator step that must be re-runnable without touching
    the steps before it. Unknown table names raise ValueError.
    """
    known = {t.name for t in Base.metadata.sorted_tables}
    unknown = set(names) - known
    if unknown:
        raise ValueError(f"Unknown tables: {sorted(unknown)}")
    deleted: dict[str, int] = {}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in names:
            deleted[table.name] = session.execute(delete(table)).rowcount
    session.commit()
    return deleted
