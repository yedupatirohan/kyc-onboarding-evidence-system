"""Create or drop all tables.  Run from the backend folder:

    python -m app.init_db            # create tables
    python -m app.init_db --reset    # drop everything, then create again
"""
import sys

from sqlalchemy import inspect

import app.models  # noqa: F401  (importing registers the tables)
from app.database import Base, engine


def create_all() -> None:
    Base.metadata.create_all(engine)


def drop_all() -> None:
    Base.metadata.drop_all(engine)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        drop_all()
        print("Dropped all tables.")
    create_all()
    tables = sorted(inspect(engine).get_table_names())
    print(f"Database: {engine.url}")
    print(f"{len(tables)} tables:")
    for name in tables:
        print(f"  - {name}")
