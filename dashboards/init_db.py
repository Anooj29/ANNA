"""Create tables and seed the bed pool. Safe to re-run at any time -
existing beds/patients are left untouched; only missing beds are added.

    python -m dashboards.init_db
"""

from __future__ import annotations

import logging

from .common.config import config
from .common.database import Base, SessionLocal, engine
from .common.models import Bed

logging.basicConfig(level=logging.INFO, format="[init_db] %(message)s")
logger = logging.getLogger(__name__)


def run() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = {bed_number for (bed_number,) in db.query(Bed.bed_number).all()}
        added = 0
        for bed_number in range(1, config.total_beds + 1):
            if bed_number not in existing:
                db.add(Bed(bed_number=bed_number, is_occupied=False))
                added += 1
        db.commit()
        logger.info("Schema ready. %d new bed(s) seeded (%d configured via HOSPITAL_TOTAL_BEDS).",
                    added,
                    config.total_beds,
                )
    finally:
        db.close()


if __name__ == "__main__":
    run()
