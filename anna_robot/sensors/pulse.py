"""Placeholder pulse reading.

The current hardware does not include a real pulse sensor; this generates a
plausible resting heart rate so the rest of the pipeline (telemetry, health
summary) has a value to work with. Replace this with a real PPG/pulse-
oximeter reading before relying on it for anything beyond a demo.
"""

from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)


class SimulatedPulseSensor:
    def read_bpm(self) -> str:
        logger.warning("Using a simulated pulse reading - no real pulse sensor is connected.")
        return f"{75 + random.randint(-5, 5)} BPM"
