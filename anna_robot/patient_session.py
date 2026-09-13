"""Per-patient session state.

Replaces the scattered `name` / `emotion` / `temp` / `pulse` / `ecg` /
`health_report` / `health_answers` globals from the original prototype.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

UNSET = "--"


@dataclass
class PatientSession:
    name: str = UNSET
    emotion: str = UNSET
    temperature: str = UNSET
    pulse: str = UNSET
    ecg: str = UNSET
    health_report: str = UNSET
    clinical_report: str = UNSET
    answers: Dict[str, str] = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)

    def reset(self) -> None:
        """Clear everything for the next patient."""
        self.name = UNSET
        self.emotion = UNSET
        self.clear_readings()
        self.started_at = time.monotonic()

    def clear_readings(self) -> None:
        """Clear the measurements but keep who the patient is."""
        self.temperature = UNSET
        self.pulse = UNSET
        self.ecg = UNSET
        self.health_report = UNSET
        self.clinical_report = UNSET
        self.answers = {}

    @property
    def is_identified(self) -> bool:
        return self.name != UNSET

    @property
    def duration_s(self) -> float:
        return max(time.monotonic() - self.started_at, 0.0)

    def to_telemetry(
        self, distance: float, state: str, extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """The status packet sent to the companion app each loop.

        Every key the original packet carried is still here, so existing
        companion apps keep working; new keys are additive.
        """
        payload: Dict[str, Any] = {
            "distance": distance,
            "temp": self.temperature,
            "pulse": self.pulse,
            "ecg": self.ecg,
            "name": self.name,
            "emotion": self.emotion,
            "state": state,
            "sleep": self.answers.get("sleep", UNSET),
            "water": self.answers.get("water", UNSET),
            "pain": self.answers.get("pain", UNSET),
            "appetite": self.answers.get("appetite", UNSET),
            "exercise": self.answers.get("exercise", UNSET),
            "stress": self.answers.get("stress", UNSET),
            "health_report": self.health_report,
            "clinical_report": self.clinical_report,
        }
        if extra:
            payload.update(extra)
        return payload
