"""Per-patient session state.

Replaces the scattered `name` / `emotion` / `temp` / `pulse` / `ecg` /
`health_report` / `health_answers` globals from the original prototype.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PatientSession:
    name: str = "--"
    emotion: str = "--"
    temperature: str = "--"
    pulse: str = "--"
    ecg: str = "--"
    health_report: str = "--"
    clinical_report: str = "--"
    answers: Dict[str, str] = field(default_factory=dict)

    def reset(self) -> None:
        self.name = "--"
        self.emotion = "--"
        self.temperature = "--"
        self.pulse = "--"
        self.ecg = "--"
        self.health_report = "--"
        self.clinical_report = "--"
        self.answers = {}

    def to_telemetry(self, distance: float, state: str) -> Dict[str, object]:
        return {
            "distance": distance,
            "temp": self.temperature,
            "pulse": self.pulse,
            "ecg": self.ecg,
            "name": self.name,
            "emotion": self.emotion,
            "state": state,
            "sleep": self.answers.get("sleep", "--"),
            "water": self.answers.get("water", "--"),
            "pain": self.answers.get("pain", "--"),
            "appetite": self.answers.get("appetite", "--"),
            "exercise": self.answers.get("exercise", "--"),
            "stress": self.answers.get("stress", "--"),
            "health_report": self.health_report,
            "clinical_report": self.clinical_report,
        }
