"""Configurable prototype monitoring thresholds; these are not diagnoses."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdProfile:
    name: str = "prototype_general_adult"
    version: str = "1.0"
    temperature_high: float = 38.0
    temperature_urgent: float = 39.0
    pulse_low: float = 50.0
    pulse_high: float = 105.0
    pulse_urgent_high: float = 125.0
    spo2_low: float = 94.0
    spo2_urgent: float = 92.0
    stale_hours: float = 4.0
    repeat_window_hours: float = 2.0


def current_profile() -> ThresholdProfile:
    return ThresholdProfile(
        temperature_high=float(os.environ.get("ANNA_TEMP_HIGH_C", "38")),
        temperature_urgent=float(os.environ.get("ANNA_TEMP_URGENT_C", "39")),
        pulse_low=float(os.environ.get("ANNA_PULSE_LOW_BPM", "50")),
        pulse_high=float(os.environ.get("ANNA_PULSE_HIGH_BPM", "105")),
        pulse_urgent_high=float(os.environ.get("ANNA_PULSE_URGENT_BPM", "125")),
        spo2_low=float(os.environ.get("ANNA_SPO2_LOW_PERCENT", "94")),
        spo2_urgent=float(os.environ.get("ANNA_SPO2_URGENT_PERCENT", "92")),
        stale_hours=float(os.environ.get("ANNA_STALE_HOURS", "4")),
        repeat_window_hours=float(os.environ.get("ANNA_REPEAT_WINDOW_HOURS", "2")),
    )
