"""SQLAlchemy engine/session wiring, shared by every dashboard."""

from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import config

# SQLite's default driver only allows the connection to be used from the
# thread that created it; FastAPI serves each request from a thread pool,
# so without this a second request would raise "SQLite objects created in
# a thread can only be used in that same thread". Postgres doesn't need
# (or accept) this argument.
connect_args = {"check_same_thread": False} if config.database_url.startswith("sqlite") else {}

engine = create_engine(config.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session, always closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
