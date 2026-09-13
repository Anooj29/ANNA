"""Parse robot measurements without manufacturing clinical values."""
from __future__ import annotations

import math
from dataclasses import dataclass

VALID_STATUSES = {"measured", "poor_signal", "sensor_error", "invalid", "not_available", "simulated"}


@dataclass(frozen=True)
class Measurement:
    value: float | None
    status: str
    quality: float | None = None


def parse_measurement(raw: str | float | None, unit: str, minimum: float, maximum: float,
                      reported_status: str | None = None, quality: float | None = None,
                      simulated: bool = False) -> Measurement:
    status = reported_status.lower() if reported_status else None
    if status and status not in VALID_STATUSES:
        return Measurement(None, "invalid", quality)
    if status in {"sensor_error", "invalid", "not_available"}:
        return Measurement(None, status, quality)
    if raw is None or not str(raw).strip():
        return Measurement(None, "not_available" if status is None else "invalid", quality)
    text = str(raw).strip().upper().replace("°", "")
    if text.endswith(unit.upper()):
        text = text[:-len(unit)].strip()
    try:
        number = float(text)
    except ValueError:
        return Measurement(None, "invalid", quality)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        return Measurement(None, "invalid", quality)
    if simulated or status == "simulated":
        return Measurement(number, "simulated", quality)
    if status == "poor_signal" or (quality is not None and quality < 50):
        return Measurement(number, "poor_signal", quality)
    return Measurement(number, "measured", quality)


def display(value: float | None, unit: str) -> str:
    return f"{value:g} {unit}" if value is not None else "not available"
