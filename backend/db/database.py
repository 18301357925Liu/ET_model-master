"""
SQLAlchemy engine and session management.
Creates all tables on startup.
"""
from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import DATABASE_URL

# ── Engine ───────────────────────────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Enable WAL mode for better concurrency
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Dependency ────────────────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_add_role_column() -> None:
    """Add role column to existing users table if missing."""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(32) DEFAULT 'user' NOT NULL"))
            conn.commit()
        except Exception:
            pass  # Column already exists or other error - ignore


# ── Init tables ───────────────────────────────────────────────────────────────

def init_db() -> None:
    """Import all models and create tables."""
    from backend.db import models  # noqa: F401
    from backend.db import models_extra  # noqa: F401

    # Ensure backend/ is on path
    import sys

    backend_path = str(Path(__file__).resolve().parent.parent)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    Base.metadata.create_all(bind=engine)
    _migrate_add_role_column()
