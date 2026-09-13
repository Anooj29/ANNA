"""Normalized chronological patient events from existing hospital records."""
from __future__ import annotations

from sqlalchemy.orm import Session

from dashboards.common.models import Alert, ClinicalNote, MedicalSummary, Medication, Patient, RobotTask, VitalReading


def get_all_timeline_events(db: Session, patient: Patient) -> list[dict]:
    events = [{"event_type": "ADMISSION", "title": "Patient admitted", "timestamp": patient.admission_date.isoformat(), "source": "Reception"}]
    if patient.discharge_date:
        events.append({"event_type": "DISCHARGE", "title": "Patient discharged", "timestamp": patient.discharge_date.isoformat(), "source": "Reception"})
    for task in db.query(RobotTask).filter(RobotTask.patient_id == patient.id).all():
        events.append({"event_type": "ANNA_TASK_CREATED", "title": f"ANNA task #{task.id} queued", "timestamp": task.assigned_at.isoformat(), "source": "ANNA"})
        if task.started_at:
            events.append({"event_type": "ANNA_VISIT_STARTED", "title": f"ANNA task #{task.id} started", "timestamp": task.started_at.isoformat(), "source": "ANNA"})
        if task.completed_at:
            events.append({"event_type": "ANNA_VISIT_COMPLETED" if task.status == "completed" else "ANNA_TASK_FAILED", "title": f"ANNA task #{task.id} {task.status}", "timestamp": task.completed_at.isoformat(), "source": "ANNA"})
    for vital in db.query(VitalReading).filter(VitalReading.patient_id == patient.id).all():
        events.append({"event_type": "VITALS_RECORDED", "title": "Measurements received", "timestamp": vital.recorded_at.isoformat(), "source": vital.source, "related_entity": vital.id})
    for alert in db.query(Alert).filter(Alert.patient_id == patient.id).all():
        events.append({"event_type": "ALERT_CREATED", "title": alert.message, "timestamp": alert.created_at.isoformat(), "source": alert.source or "Monitoring", "severity": alert.severity, "related_entity": alert.id})
        if alert.acknowledged_at:
            events.append({"event_type": "ALERT_ACKNOWLEDGED", "title": "Alert acknowledged", "timestamp": alert.acknowledged_at.isoformat(), "source": alert.acknowledged_by or "Clinician", "related_entity": alert.id})
        if alert.resolved_at:
            events.append({"event_type": "ALERT_RESOLVED", "title": "Alert resolved", "timestamp": alert.resolved_at.isoformat(), "source": alert.resolved_by or "Clinician", "related_entity": alert.id})
    for med in db.query(Medication).filter(Medication.patient_id == patient.id).all():
        events.append({"event_type": "MEDICATION_ADDED", "title": f"Medication added: {med.medicine_name}", "timestamp": med.start_date.isoformat(), "source": "Clinician", "related_entity": med.id})
    for note in db.query(ClinicalNote).filter(ClinicalNote.patient_id == patient.id).all():
        events.append({"event_type": "CLINICAL_NOTE", "title": "Clinical note added", "timestamp": note.created_at.isoformat(), "source": note.author_name, "related_entity": note.id})
    for summary in db.query(MedicalSummary).filter(MedicalSummary.patient_id == patient.id).all():
        events.append({"event_type": "ANNA_SUMMARY", "title": "ANNA assistive summary available", "timestamp": summary.created_at.isoformat(), "source": "ANNA", "related_entity": summary.id})
    return sorted(events, key=lambda item: item["timestamp"], reverse=True)


def patient_timeline(db: Session, patient: Patient, limit: int = 100) -> list[dict]:
    return get_all_timeline_events(db, patient)[:limit]


def patient_timeline_paged(
    db: Session,
    patient: Patient,
    page: int = 1,
    page_size: int = 50,
    event_type: str | None = None,
) -> dict:
    events = get_all_timeline_events(db, patient)
    if event_type:
        filter_type = event_type.strip().upper()
        events = [e for e in events if filter_type in e.get("event_type", "").upper()]
    total = len(events)
    page_size = max(1, page_size)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = max(0, (page - 1) * page_size)
    items = events[start : start + page_size]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
