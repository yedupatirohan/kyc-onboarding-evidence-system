"""Export small, committable seed files into data/seed/ (the 31 MB database itself stays git-ignored).

    python -m generator.export_seed          (run after python -m validation.reproducibility)

Creates: reference_data.sql (master data as INSERT statements), sample_*.csv (first rows of key tables),
and copies ground_truth.csv/json, validation_report.* and reproducibility.json from data/output.
"""
import csv
import shutil
import sqlite3

from app.config import PROJECT_ROOT, settings

SAMPLES = {"customer": 200, "document": 400, "ownership_link": 200, "review_case": 200, "alert": 200}


def _sql_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(int(value)) if isinstance(value, int) else repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def main() -> None:
    out, seed_dir = PROJECT_ROOT / "data" / "output", PROJECT_ROOT / "data" / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    url = settings.resolved_database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit("export_seed supports SQLite only")
    connection = sqlite3.connect(url.replace("sqlite:///", "", 1))

    lines = ["-- Master (reference) data. Load into the schema created by python -m app.init_db", ""]
    for table in ("customer_type", "kyc_requirement", "customer_type_requirement"):
        cursor = connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2" if table == "customer_type_requirement"
                                    else f"SELECT * FROM {table} ORDER BY 1")
        names = [d[0] for d in cursor.description]
        for row in cursor:
            lines.append(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(_sql_value(v) for v in row)});")
        lines.append("")
    (seed_dir / "reference_data.sql").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    for table, limit in SAMPLES.items():
        cursor = connection.execute(f"SELECT * FROM {table} ORDER BY 1 LIMIT {limit}")
        with open(seed_dir / f"sample_{table}.csv", "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow([d[0] for d in cursor.description])
            writer.writerows(cursor)

    copied = []
    for name in ("ground_truth.csv", "ground_truth.json", "validation_report.json", "validation_report.md", "reproducibility.json"):
        if (out / name).exists():
            shutil.copyfile(out / name, seed_dir / name)
            copied.append(name)
    print(f"Wrote reference_data.sql, {len(SAMPLES)} sample CSVs and copied {copied} to {seed_dir}")


if __name__ == "__main__":
    main()
