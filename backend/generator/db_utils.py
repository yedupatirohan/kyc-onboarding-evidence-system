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
