"""Transparent operational attention classification from stored facts."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from dashboards.common.models import Alert, Patient, VitalReading
from .thresholds import current_profile

RANK = {"STABLE": 0, "OBSERVE": 1, "REVIEW": 2, "URGENT": 3, "CRITICAL": 4}


def patient_contexts(db: Session, patient_ids: list[int]) -> tuple[dict[int, list[VitalReading]], dict[int, list[Alert]]]:
    """Load bounded recent readings and active alerts in two queries for a roster."""
    readings_by_patient = defaultdict(list)
    alerts_by_patient = defaultdict(list)
    if not patient_ids:
        return readings_by_patient, alerts_by_patient
    ranked = db.query(VitalReading.id.label("id"), func.row_number().over(
        partition_by=VitalReading.patient_id,
        order_by=(VitalReading.recorded_at.desc(), VitalReading.id.desc())).label("position")
    ).filter(VitalReading.patient_id.in_(patient_ids)).subquery()
    for reading in db.query(VitalReading).join(ranked, ranked.c.id == VitalReading.id).filter(
        ranked.c.position <= 30).order_by(VitalReading.patient_id, VitalReading.recorded_at.desc()).all():
        readings_by_patient[reading.patient_id].append(reading)
    for alert in db.query(Alert).filter(Alert.patient_id.in_(patient_ids),
                                      Alert.status.in_(["new", "active", "under_review"])).all():
        alerts_by_patient[alert.patient_id].append(alert)
    return readings_by_patient, alerts_by_patient


def assess_patient(db: Session, patient: Patient, now: dt.datetime | None = None,
                   readings: list[VitalReading] | None = None,
                   alerts: list[Alert] | None = None) -> dict:
    now = now or dt.datetime.utcnow()
    profile = current_profile()
    if readings is None:
        readings = db.query(VitalReading).filter(VitalReading.patient_id == patient.id).order_by(VitalReading.recorded_at.desc()).limit(30).all()
    valid = [v for v in readings if v.quality_status != "simulated"]
    latest = valid[0] if valid else None
    level = "STABLE"
    reasons: list[str] = []

    def raise_to(candidate: str, reason: str):
        nonlocal level
        if RANK[candidate] > RANK[level]:
            level = candidate
        reasons.append(reason)

    if alerts is None:
        alerts = db.query(Alert).filter(Alert.patient_id == patient.id, Alert.status.in_(["new", "active", "under_review"])).all()
    if any(a.severity.upper() == "CRITICAL" for a in alerts):
        raise_to("CRITICAL", "Unacknowledged critical monitoring alert")
    elif any(a.severity.upper() == "URGENT" for a in alerts):
        raise_to("URGENT", "Unacknowledged urgent monitoring alert")
    elif alerts:
        raise_to("REVIEW", f"{len(alerts)} active monitoring alert(s)")

    if latest:
        if latest.temperature_status == "measured" and latest.temperature_c is not None:
            if latest.temperature_c >= profile.temperature_urgent:
                raise_to("URGENT", f"Temperature {latest.temperature_c:g} °C exceeds configured urgent threshold")
            elif latest.temperature_c >= profile.temperature_high:
                raise_to("REVIEW", f"Temperature {latest.temperature_c:g} °C exceeds configured high threshold")
        if latest.pulse_status == "measured" and latest.pulse_bpm is not None:
            if latest.pulse_bpm >= profile.pulse_urgent_high:
                raise_to("URGENT", f"Heart rate {latest.pulse_bpm:g} BPM exceeds configured urgent threshold")
            elif latest.pulse_bpm < profile.pulse_low or latest.pulse_bpm >= profile.pulse_high:
                raise_to("REVIEW", f"Heart rate {latest.pulse_bpm:g} BPM is outside configured monitoring range")
        if latest.spo2_status == "measured" and latest.spo2_percent is not None:
            if latest.spo2_percent < profile.spo2_urgent:
                raise_to("URGENT", f"SpO2 {latest.spo2_percent:g}% is below configured urgent threshold")
            elif latest.spo2_percent < profile.spo2_low:
                raise_to("REVIEW", f"SpO2 {latest.spo2_percent:g}% is below configured low threshold")
        if any(s in {"poor_signal", "sensor_error", "invalid"} for s in (latest.temperature_status, latest.pulse_status, latest.spo2_status)):
            raise_to("OBSERVE", "One or more measurements need repeating")
        if (now - latest.recorded_at).total_seconds() > profile.stale_hours * 3600:
            raise_to("OBSERVE", "Latest check is older than configured freshness limit")
    else:
        raise_to("OBSERVE", "No reliable ANNA measurement is available")

    return {"level": level, "reasons": reasons, "assessed_at": now.isoformat(),
            "rule_version": profile.version, "threshold_profile": profile.name,
            "latest_measured_at": latest.recorded_at.isoformat() if latest else None}
