"""Placeholder pulse reading.

The current hardware does not include a real pulse sensor; this generates a
plausible resting heart rate so the rest of the pipeline (telemetry, health
summary) has a value to work with. Replace this with a real PPG/pulse-
oximeter reading before relying on it for anything beyond a demo.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)


class SimulatedPulseSensor:
    """A stand-in pulse sensor. The value is invented, and says so."""

    def __init__(self, resting_bpm: int = 75, variation: int = 5) -> None:
        self._resting_bpm = int(resting_bpm)
        self._variation = abs(int(variation))
        self._warned = False
        self.last_bpm: Optional[int] = None

    @property
    def is_simulated(self) -> bool:
        return True

    def read_bpm(self) -> str:
        # Warn once per process rather than on every reading: the old
        # per-call warning buried real problems in the log.
        if not self._warned:
            logger.warning(
                "Pulse readings are SIMULATED - no pulse sensor is connected. "
                "They must not be used clinically."
            )
            self._warned = True
        self.last_bpm = self._resting_bpm + random.randint(-self._variation, self._variation)
        return f"{self.last_bpm} BPM"
