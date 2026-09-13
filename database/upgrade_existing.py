"""Back up, rehearse, and optionally upgrade a PostgreSQL installation.

Use only after checking that the schema is the original ANNA baseline. The
rehearsal restores a custom pg_dump into a throwaway database and compares row
counts. An unsuccessful rehearsal never stamps the source database.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
import shutil
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text

from dashboards.common.config import config
from dashboards.common.database import engine


CORE_TABLES = ("users", "patients", "beds", "vital_readings", "robot_tasks", "alerts", "audit_logs", "medications")


def postgres_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidate = Path("C:/Program Files/PostgreSQL/18/bin") / f"{name}.exe"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError(f"{name} is required for a verified PostgreSQL backup and rehearsal")


def run_command(args: list[str], env: dict[str, str]) -> None:
    result = subprocess.run(args, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed: {result.stderr[-1000:]}")


def row_counts(connection) -> dict[str, int]:
    return {name: connection.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one() for name in CORE_TABLES}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="upgrade source after successful rehearsal")
    args = parser.parse_args()
    if config.db_engine != "postgres":
        raise RuntimeError("ANNA hospital software requires PostgreSQL.")
    existing = set(inspect(engine).get_table_names())
    if not set(CORE_TABLES).issubset(existing):
        raise RuntimeError("Expected an existing ANNA database with all core tables.")
    with engine.connect() as connection:
        baseline = row_counts(connection)
        current_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none() if "alembic_version" in existing else None
        plaintext_only = connection.execute(text(
            "SELECT COUNT(*) FROM patients WHERE portal_pin IS NOT NULL AND portal_pin_hash IS NULL")).scalar_one()
    if current_revision not in {None, "0003", "0004"}:
        raise RuntimeError(f"Expected unversioned baseline or revision 0003/0004; found {current_revision}.")
    if plaintext_only:
        raise RuntimeError("Backfill plaintext-only portal PINs before upgrading.")

    suffix = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    stage_name = f"anna_upgrade_rehearsal_{suffix}"
    backup_dir = Path.home() / "ANNA-backups"
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    backup = backup_dir / f"anna_before_{suffix}.dump"
    child_env = {**os.environ, "PGPASSWORD": config.postgres_password}
    run_command([postgres_tool("pg_dump"), "--format=custom", "--no-owner", "--no-privileges",
                 "--host", config.postgres_host, "--port", str(config.postgres_port),
                 "--username", config.postgres_user, "--file", str(backup), config.postgres_db], child_env)
    if backup.stat().st_size < 1024:
        raise RuntimeError("Backup appears incomplete; source was not modified.")
    print(f"Verified backup: {backup} ({backup.stat().st_size} bytes)")

    maintenance = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    stage_engine = None
    try:
        with maintenance.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{stage_name}"'))
        run_command([postgres_tool("pg_restore"), "--no-owner", "--no-privileges",
                     "--host", config.postgres_host, "--port", str(config.postgres_port),
                     "--username", config.postgres_user, "--dbname", stage_name, str(backup)], child_env)
        stage_env = {**child_env, "POSTGRES_DB": stage_name}
        if current_revision is None:
            run_command([sys.executable, "-m", "alembic", "stamp", "0001"], stage_env)
        run_command([sys.executable, "-m", "alembic", "upgrade", "head"], stage_env)
        stage_engine = create_engine(engine.url.set(database=stage_name))
        with stage_engine.connect() as connection:
            if row_counts(connection) != baseline:
                raise RuntimeError("Rehearsal row counts changed; source was not modified.")
            if connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != "0005":
                raise RuntimeError("Rehearsal did not reach revision 0005.")
        print(f"Rehearsal passed; preserved core row counts: {baseline}")
        if args.apply:
            if current_revision is None:
                run_command([sys.executable, "-m", "alembic", "stamp", "0001"], child_env)
            run_command([sys.executable, "-m", "alembic", "upgrade", "head"], child_env)
            with engine.connect() as connection:
                if row_counts(connection) != baseline:
                    raise RuntimeError("Source row counts differ after upgrade; restore the verified backup.")
            print("Source upgraded to revision 0005; core row counts preserved.")
        else:
            print("Source database unchanged. Pass --apply to upgrade after rehearsal.")
    finally:
        if stage_engine is not None:
            stage_engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{stage_name}" WITH (FORCE)'))
        maintenance.dispose()


if __name__ == "__main__":
    main()
