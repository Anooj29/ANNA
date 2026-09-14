"""GPIO-free stand-ins for motors and sensors (software-only bring-up on a Pi)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SimulatedMotorController:
    def forward(self) -> None:
        logger.debug("[sim] motor: forward")

    def turn_left(self) -> None:
        logger.debug("[sim] motor: left")

    def turn_right(self) -> None:
        logger.debug("[sim] motor: right")

    def stop(self) -> None:
        logger.debug("[sim] motor: stop")


class SimulatedUltrasonicSensor:
    """Returns a fixed distance so SEARCH can reach face interaction without an HC-SR04."""

    def __init__(self, distance_cm: float) -> None:
        self._distance_cm = distance_cm

    def measure_cm(self) -> float:
        return self._distance_cm


class SimulatedEcgSensor:
    def record_and_analyze(self) -> str:
        logger.info("[sim] ECG reading (no ADS1115 / leads connected).")
        return "Normal Sinus Rhythm (simulated)"
