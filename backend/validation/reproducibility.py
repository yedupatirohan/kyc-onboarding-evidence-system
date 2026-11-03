"""Prove reproducibility: run the whole pipeline twice with the same seed and compare.

    python -m validation.reproducibility
"""
import hashlib
import json
from pathlib import Path

from app.config import PROJECT_ROOT, settings


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(result: dict) -> dict:
    paths, checks = result["paths"], result["report"]["reproducibility_checksums"]
    return {
        "baseline_database_sha256": checks["baseline_overall"],
        "final_database_sha256": checks["final_overall"],
        "ground_truth_csv_sha256": _sha(Path(paths["csv"])),
        "ground_truth_json_sha256": _sha(Path(paths["json"])),
        "validation_report_json_sha256": _sha(Path(paths["json"]).parent / "validation_report.json"),
        "validation_report_md_sha256": _sha(Path(paths["json"]).parent / "validation_report.md"),
    }


def run_twice(session_factory, out_dir: Path | None = None, **pipeline_kwargs) -> dict:
    from generator.generate import run_pipeline

    out_dir = Path(out_dir) if out_dir else PROJECT_ROOT / "data" / "output"
    runs = []
    for number in (1, 2):
        with session_factory() as session:
            runs.append(_fingerprint(run_pipeline(session, out_dir=out_dir, log=lambda *_: None, **pipeline_kwargs)))
    identical = runs[0] == runs[1]
    return {"seed": settings.seed, "identical": identical, "run_1": runs[0], "run_2": runs[1],
            "differences": [k for k in runs[0] if runs[0][k] != runs[1][k]]}


def main() -> None:
    from app.database import SessionLocal

    result = run_twice(SessionLocal)
    out = PROJECT_ROOT / "data" / "output"
    (out / "reproducibility.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Seed {result['seed']}: two full runs identical = {result['identical']}")
    for key, value in result["run_1"].items():
        print(f"  {key:<32} {value}")
    if not result["identical"]:
        raise SystemExit(f"DIFFERENCES: {result['differences']}")


if __name__ == "__main__":
    main()
