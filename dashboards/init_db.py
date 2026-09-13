"""Apply hospital schema migrations, then idempotently seed bed capacity."""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .common.config import config
from .common.database import SessionLocal, engine
from .common.models import Bed

logger = logging.getLogger(__name__)


def run() -> None:
    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        raise RuntimeError(
            "Existing ANNA database has no Alembic revision. Back it up, "
            "backfill PINs, stamp 0001, and upgrade head as documented in database/MIGRATIONS.md."
        )
    alembic = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(alembic, "head")

    with SessionLocal.begin() as db:
        existing = {bed_number for (bed_number,) in db.query(Bed.bed_number).all()}
        for bed_number in range(1, config.total_beds + 1):
            if bed_number not in existing:
                db.add(Bed(bed_number=bed_number))
    logger.info("ANNA schema ready; configured bed capacity %d", config.total_beds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
