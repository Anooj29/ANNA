"""Disposable PostgreSQL databases for tests; never connect writes to ANNA data."""
from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

load_dotenv()


def url_for(name: str) -> URL:
    return URL.create("postgresql+psycopg2",
                      username=os.environ.get("POSTGRES_USER", "anna"),
                      password=os.environ.get("POSTGRES_PASSWORD", ""),
                      host=os.environ.get("POSTGRES_HOST", "localhost"),
                      port=int(os.environ.get("POSTGRES_PORT", "5432")),
                      database=name)


def create_test_database() -> tuple[str, URL]:
    name = f"anna_test_{uuid.uuid4().hex[:16]}"
    maintenance = create_engine(url_for("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with maintenance.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        maintenance.dispose()
    return name, url_for(name)


def drop_test_database(name: str) -> None:
    if not name.startswith("anna_test_") or len(name) > 40:
        raise ValueError("Refusing to drop a database outside the test namespace")
    maintenance = create_engine(url_for("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with maintenance.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        maintenance.dispose()
