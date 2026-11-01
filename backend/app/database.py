"""Database engine, session factory and declarative base."""
import sqlite3
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

DATABASE_URL = settings.resolved_database_url
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Make sure the folder for the SQLite file exists
if IS_SQLITE:
    db_file = DATABASE_URL.replace("sqlite:///", "", 1)
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)

# check_same_thread=False lets FastAPI use the connection across its worker threads
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite ignores foreign keys unless this PRAGMA is run on EVERY connection."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """All SQLAlchemy models inherit from this class (added in Phase 2B)."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: open a session per request, always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
