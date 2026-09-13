"""CLI entry point: ``python3 -m anna_robot.main``."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import Config
from .robot import HealthcareRobot


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # These libraries are chatty at DEBUG and drown out the robot's own log.
    for noisy in ("PIL", "matplotlib", "urllib3", "comtypes"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ANNA healthcare assistant robot controller.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="TCP port for the telemetry link (overrides ROBOT_TCP_PORT).",
    )
    parser.add_argument(
        "--log-level", default=os.environ.get("ROBOT_LOG_LEVEL", "INFO"),
        help="Logging level, e.g. DEBUG, INFO, WARNING.",
    )
    parser.add_argument(
        "--no-debug-window", action="store_true",
        help="Disable the OpenCV debug window (useful for headless / SSH-only runs).",
    )
    parser.add_argument(
        "--no-wait", action="store_true",
        help="Start without waiting for a companion app to connect.",
    )
    parser.add_argument(
        "--simulate", action="store_true",
        help="Run with simulated GPIO: no motors, servos or GPIO sensors move. "
             "Useful for testing the control logic on a desk.",
    )
    parser.add_argument(
        "--head-pan-pin", type=int, default=None,
        help="BCM pin for the head pan servo (overrides ROBOT_HEAD_PAN_PIN).",
    )
    parser.add_argument(
        "--head-tilt-pin", type=int, default=None,
        help="BCM pin for the head tilt servo (overrides ROBOT_HEAD_TILT_PIN).",
    )
    parser.add_argument(
        "--check-config", action="store_true",
        help="Print the resolved configuration, validate it, and exit without starting.",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> Config:
    """Resolve the configuration: environment first, CLI flags on top."""
    config = Config.from_env()
    if args.port is not None:
        config.tcp_port = args.port
    if args.no_debug_window:
        config.show_debug_window = False
    if args.no_wait:
        config.tcp_wait_for_client = False
    if args.simulate:
        config.simulate_hardware = True
    if args.head_pan_pin is not None:
        config.head_pan_pin = args.head_pan_pin
    if args.head_tilt_pin is not None:
        config.head_tilt_pin = args.head_tilt_pin
    return config


def main(argv=None) -> int:
    args = parse_args(argv)
    _configure_logging(args.log_level)

    config = build_config(args)
    problems = config.validate()

    if args.check_config:
        print(config.describe())
        if problems:
            print("\nProblems found:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("\nConfiguration is valid.")
        return 0

    if problems:
        for problem in problems:
            logging.error("Configuration problem: %s", problem)
        return 1

    try:
        robot = HealthcareRobot(config)
    except Exception:
        logging.exception("The robot could not start.")
        return 1

    try:
        robot.run()
    except Exception:
        # run() has already shut the hardware down in its finally block; this
        # turns a raw traceback into a clean non-zero exit for systemd/run.sh.
        logging.exception("The robot stopped because of an error.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
