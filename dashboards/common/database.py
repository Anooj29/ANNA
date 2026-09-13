"""SQLAlchemy engine/session wiring, shared by every dashboard."""

from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import config

engine = create_engine(config.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session, always closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
