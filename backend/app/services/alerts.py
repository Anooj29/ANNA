"""Deterministic threshold alerts with short-window duplicate suppression."""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from dashboards.common.models import Alert, VitalReading
from .thresholds import current_profile


def create_vital_alerts(db: Session, vital: VitalReading) -> list[Alert]:
    profile = current_profile()
    checks = (
        ("temperature", vital.temperature_c, vital.temperature_status, profile.temperature_high, "high", "Temperature"),
        ("pulse", vital.pulse_bpm, vital.pulse_status, profile.pulse_high, "high", "Heart rate"),
        ("spo2", vital.spo2_percent, vital.spo2_status, profile.spo2_low, "low", "SpO2"),
    )
    created = []
    for metric, value, status, threshold, direction, label in checks:
        if status != "measured" or value is None:
            continue
        abnormal = value >= threshold if direction == "high" else value < threshold
        if not abnormal:
            continue
        severity = "URGENT" if (
            (metric == "temperature" and value >= profile.temperature_urgent) or
            (metric == "pulse" and value >= profile.pulse_urgent_high) or
            (metric == "spo2" and value < profile.spo2_urgent)
        ) else "WARNING"
        recent = db.query(Alert).filter(
            Alert.patient_id == vital.patient_id, Alert.metric == metric,
            Alert.status.in_(["new", "active", "under_review"]),
            Alert.created_at >= vital.recorded_at - dt.timedelta(hours=profile.repeat_window_hours),
        ).order_by(Alert.created_at.desc()).first()
        if recent and recent.severity == severity:
            continue
        previous = db.query(VitalReading).filter(
            VitalReading.patient_id == vital.patient_id,
            VitalReading.id != vital.id,
            VitalReading.recorded_at < vital.recorded_at,
        ).order_by(VitalReading.recorded_at.desc()).first()
        previous_value = getattr(previous, {"temperature": "temperature_c", "pulse": "pulse_bpm", "spo2": "spo2_percent"}[metric]) if previous else None
        alert = Alert(patient_id=vital.patient_id, session_id=vital.session_id, vital_id=vital.id,
                      alert_type="Vital Threshold", severity=severity,
                      message=f"{label} {value:g} exceeds configured monitoring threshold {threshold:g}.",
                      metric=metric, actual_value=value, threshold_value=threshold,
                      previous_value=previous_value, delta=value - previous_value if previous_value is not None else None,
                      source=vital.source, status="new", created_at=vital.recorded_at)
        db.add(alert)
        created.append(alert)
    return created
