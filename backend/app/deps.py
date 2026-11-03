"""Shared FastAPI dependencies that are not database sessions."""
from pathlib import Path

from app.config import PROJECT_ROOT


def get_output_dir() -> Path:
    """Folder holding ground_truth.csv/json and validation_report.json/md (tests override this)."""
    return PROJECT_ROOT / "data" / "output"
