"""Print a SHA-256 fingerprint of the generated tables in the database.

    python -m generator.digest

Run it, regenerate, run it again: identical output means identical data.
(Phase 4 extends this into the full reproducibility report.)
"""
import hashlib
import sqlite3

from app.config import settings
from generator.db_utils import REFERENCE_TABLES


def table_digest(connection: sqlite3.Connection, table: str) -> tuple[int, str]:
    """(row count, sha256) of one table, rows sorted by every column."""
    columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
    order = ", ".join(str(i) for i in range(1, len(columns) + 1))
    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(f"SELECT * FROM {table} ORDER BY {order}"):
        digest.update(repr(row).encode("utf-8"))
        count += 1
    return count, digest.hexdigest()


def main() -> None:
    url = settings.resolved_database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit("digest only supports SQLite for now")
    path = url.replace("sqlite:///", "", 1)
    with sqlite3.connect(path) as connection:
        tables = [
            r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        overall = hashlib.sha256()
        for table in tables:
            if table in REFERENCE_TABLES:
                continue
            count, digest = table_digest(connection, table)
            overall.update(f"{table}:{digest}".encode("utf-8"))
            print(f"{table:<26} rows={count:<6} sha256={digest[:16]}...")
        print(f"{'OVERALL':<26} sha256={overall.hexdigest()}")


if __name__ == "__main__":
    main()
