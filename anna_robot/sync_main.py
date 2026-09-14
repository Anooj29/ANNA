"""Run face sync without starting the full robot (no GPIO, camera, or models loop).

Usage from repo root on the Pi:

    python3 -m anna_robot.sync_main
    python3 -m anna_robot.sync_main --loop 30
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from .config import Config
from .sync_faces import FaceSync


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync patient reference photos from the Windows hub.")
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Poll every N seconds (default: run once and exit).",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("ROBOT_LOG_LEVEL", "INFO"),
        help="Logging level, e.g. DEBUG, INFO.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _configure_logging(args.log_level)
    config = Config.from_env()
    sync = FaceSync(config)

    if args.loop <= 0:
        count = sync.sync()
        logging.getLogger(__name__).info("Done. %d new face(s) downloaded.", count)
        return

    logger = logging.getLogger(__name__)
    logger.info("Face sync loop every %d s (Ctrl+C to stop).", args.loop)
    while True:
        count = sync.sync()
        if count:
            logger.info("Downloaded %d new face(s).", count)
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
