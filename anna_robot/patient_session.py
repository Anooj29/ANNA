"""Per-patient session state.

Replaces the scattered `name` / `emotion` / `temp` / `pulse` / `ecg` /
`health_report` / `health_answers` globals from the original prototype.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
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
    answers: Dict[str, str] = field(default_factory=dict)

    def reset(self) -> None:
        self.name = "--"
        self.emotion = "--"
        self.temperature = "--"
        self.pulse = "--"
        self.ecg = "--"
        self.health_report = "--"
        self.answers = {}

    def save_to_disk(self, root_dir: str) -> str:
        """Saves the current session to a timestamped folder and returns the folder path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{self.name}_{timestamp}"
        session_path = os.path.join(root_dir, folder_name)
        os.makedirs(session_path, exist_ok=True)

        data = {
            "name": self.name,
            "emotion": self.emotion,
            "temperature": self.temperature,
            "pulse": self.pulse,
            "ecg": self.ecg,
            "health_report": self.health_report,
            "answers": self.answers,
            "timestamp": timestamp,
        }

        with open(os.path.join(session_path, "data.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        return session_path

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
        }
