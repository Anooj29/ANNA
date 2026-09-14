"""CLI entry point: `python3 -m anna_robot.main`."""

from __future__ import annotations

import argparse
import logging
import os

from .config import Config
from .robot import HealthcareRobot


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Healthcare assistant robot controller.")
    parser.add_argument("--port", type=int, default=None, help="TCP port for the telemetry link (overrides ROBOT_TCP_PORT).")
    parser.add_argument(
        "--log-level", default=os.environ.get("ROBOT_LOG_LEVEL", "INFO"),
        help="Logging level, e.g. DEBUG, INFO, WARNING.",
    )
    parser.add_argument(
        "--no-debug-window", action="store_true",
        help="Disable the OpenCV debug window (useful for headless / SSH-only runs).",
    )
    parser.add_argument(
        "--simulate-hardware", action="store_true",
        help="Do not use GPIO, motors, ultrasonic, or ECG hardware (software-only test run).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _configure_logging(args.log_level)

    config = Config.from_env()
    if args.port is not None:
        config.tcp_port = args.port
    if args.no_debug_window:
        config.show_debug_window = False
    if args.simulate_hardware:
        config.simulate_hardware = True

    robot = HealthcareRobot(config)
    robot.run()


if __name__ == "__main__":
    main()
