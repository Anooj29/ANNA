"""Quality-aware patient trends and visit comparison from stored measurements."""
from __future__ import annotations

import datetime as dt
from statistics import mean

from sqlalchemy.orm import Session

from dashboards.common.models import HealthCheckSession, PatientResponse, VitalReading

METRICS = {
    "temperature": ("temperature_c", "temperature_status", "°C"),
    "pulse": ("pulse_bpm", "pulse_status", "BPM"),
    "spo2": ("spo2_percent", "spo2_status", "%"),
}
RANGES = {"6h": dt.timedelta(hours=6), "24h": dt.timedelta(hours=24), "7d": dt.timedelta(days=7), "30d": dt.timedelta(days=30)}


def trend_summary(db: Session, patient_id: int, range_key: str = "24h", now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.utcnow()
    if range_key not in RANGES:
        raise ValueError("Unsupported range")
    readings = db.query(VitalReading).filter(
        VitalReading.patient_id == patient_id,
        VitalReading.recorded_at >= now - RANGES[range_key],
        VitalReading.quality_status != "simulated",
    ).order_by(VitalReading.recorded_at.asc()).all()
    result = {}
    for name, (column, status_column, unit) in METRICS.items():
        series = [{"value": getattr(v, column), "measured_at": v.recorded_at.isoformat(),
                   "source": v.source, "quality": getattr(v, name + "_quality")}
                  for v in readings if getattr(v, status_column) == "measured" and getattr(v, column) is not None]
        values = [point["value"] for point in series]
        current = values[-1] if values else None
        previous = values[-2] if len(values) >= 2 else None
        result[name] = {
            "unit": unit, "current": current, "previous": previous,
            "delta": round(current - previous, 2) if previous is not None else None,
            "direction": "up" if previous is not None and current > previous else "down" if previous is not None and current < previous else "steady" if previous is not None else None,
            "average": round(mean(values), 2) if values else None,
            "min": min(values) if values else None, "max": max(values) if values else None,
            "sample_count": len(values), "last_measured_at": series[-1]["measured_at"] if series else None,
            "source": series[-1]["source"] if series else None,
            "quality": series[-1]["quality"] if series else None,
            "series": series,
        }
    return {"range": range_key, "generated_at": now.isoformat(), "metrics": result}


def compare_visits(db: Session, patient_id: int) -> dict:
    sessions = db.query(HealthCheckSession).filter(
        HealthCheckSession.patient_id == patient_id,
        HealthCheckSession.status == "completed",
    ).order_by(HealthCheckSession.completed_at.desc()).limit(30).all()
    readings = {}
    eligible = []
    for session in sessions:
        reading = db.query(VitalReading).filter(
            VitalReading.session_id == session.id, VitalReading.quality_status != "simulated"
        ).order_by(VitalReading.recorded_at.desc()).first()
        if reading and any(getattr(reading, status) == "measured" for _, status, _ in METRICS.values()):
            eligible.append(session)
            readings[session.id] = reading
            if len(eligible) == 2:
                break
    if len(eligible) < 2:
        return {"previous_available": False, "message": "No previous reliable measurement available.", "metrics": {}}
    latest, previous = eligible
    metrics = {}
    for name, (column, status_column, unit) in METRICS.items():
        current_reading, previous_reading = readings[latest.id], readings[previous.id]
        current = getattr(current_reading, column) if current_reading and getattr(current_reading, status_column) == "measured" else None
        old = getattr(previous_reading, column) if previous_reading and getattr(previous_reading, status_column) == "measured" else None
        metrics[name] = {"previous": old, "current": current,
                         "delta": round(current - old, 2) if current is not None and old is not None else None,
                         "unit": unit}
    def symptoms(session_id):
        rows = db.query(PatientResponse).filter(PatientResponse.session_id == session_id).all()
        return {r.answer.strip().lower() for r in rows if any(word in r.question.lower() for word in ("symptom", "pain", "discomfort")) and r.answer.strip()}
    old_symptoms, new_symptoms = symptoms(previous.id), symptoms(latest.id)
    return {"previous_available": True, "previous_visit_at": previous.completed_at.isoformat() if previous.completed_at else None,
            "current_visit_at": latest.completed_at.isoformat() if latest.completed_at else None,
            "metrics": metrics, "symptoms": {"new": sorted(new_symptoms - old_symptoms), "resolved": sorted(old_symptoms - new_symptoms)}}
