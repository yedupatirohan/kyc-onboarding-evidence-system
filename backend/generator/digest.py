"""SHA-256 fingerprints of the generated tables (the reproducibility evidence).

    python -m generator.digest

Run it, regenerate, run it again: identical output means identical data.
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


def compute_digests(connection: sqlite3.Connection) -> dict:
    """{'tables': {name: {'rows': n, 'sha256': hex}}, 'overall': hex} for generated tables."""
    names = [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    overall = hashlib.sha256()
    tables = {}
    for name in names:
        if name in REFERENCE_TABLES:
            continue
        count, digest = table_digest(connection, name)
        overall.update(f"{name}:{digest}".encode("utf-8"))
        tables[name] = {"rows": count, "sha256": digest}
    return {"tables": tables, "overall": overall.hexdigest()}


def main() -> None:
    url = settings.resolved_database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit("digest only supports SQLite for now")
    with sqlite3.connect(url.replace("sqlite:///", "", 1)) as connection:
        result = compute_digests(connection)
    for name, info in result["tables"].items():
        print(f"{name:<26} rows={info['rows']:<6} sha256={info['sha256'][:16]}...")
    print(f"{'OVERALL':<26} sha256={result['overall']}")


if __name__ == "__main__":
    main()
