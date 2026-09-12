"""Clinician Dashboard API routes: patient analytics, task orchestration, alerts."""

from __future__ import annotations

import datetime as dt
import logging
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from dashboards.common.database import get_db
from dashboards.common.models import (
    Alert,
    AuditLog,
    Bed,
    EmotionRecord,
    HealthCheckSession,
    MedicalSummary,
    Medication,
    MedicationLog,
    Patient,
    PatientResponse,
    RobotTask,
    VitalReading,
)
from ..auth import get_current_user, hash_password
from ..schemas import (
    AlertAcknowledgeRequest,
    AlertResponseModel,
    MedicationCreateRequest,
    MedicationResponseModel,
    PatientResponseModel,
    TaskCreateRequest,
    TaskResponseModel,
)
from ..websocket import ws_manager

logger = logging.getLogger("anna.clinician")
router = APIRouter(prefix="/api", tags=["clinician"])


def calculate_risk(patient: Patient, db: Session) -> str:
    """Evaluate patient vital trends and open alerts for risk categorization."""
    active_urgent_alerts = (
        db.query(Alert)
        .filter(Alert.patient_id == patient.id, Alert.status == "active", Alert.severity == "URGENT")
        .count()
    )
    if active_urgent_alerts > 0:
        return "URGENT"

    latest_vital = (
        db.query(VitalReading)
        .filter(VitalReading.patient_id == patient.id)
        .order_by(VitalReading.recorded_at.desc())
        .first()
    )
    if latest_vital:
        if latest_vital.temperature_c >= 38.0 or latest_vital.pulse_bpm >= 105 or latest_vital.spo2_percent < 94.0:
            return "WARNING"
        if latest_vital.ecg_note and "Irregular" in latest_vital.ecg_note:
            return "WARNING"

    active_warning_alerts = (
        db.query(Alert)
        .filter(Alert.patient_id == patient.id, Alert.status == "active", Alert.severity == "WARNING")
        .count()
    )
    if active_warning_alerts > 0:
        return "WARNING"

    return "NORMAL"


@router.get("/clinician/stats")
def clinician_stats(db: Session = Depends(get_db)):
    active_patients = db.query(Patient).filter(Patient.status == "admitted").count()
    pending_tasks = (
        db.query(RobotTask)
        .filter(RobotTask.status.in_(["queued", "in_progress"]))
        .count()
    )

    today_start = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    completed_today = (
        db.query(HealthCheckSession)
        .filter(HealthCheckSession.completed_at >= today_start)
        .count()
    )

    urgent_alerts = (
        db.query(Alert)
        .filter(Alert.status == "active", Alert.severity == "URGENT")
        .count()
    )

    # Patients needing attention (abnormal vitals or active alerts)
    attention_count = (
        db.query(Patient.id)
        .join(Alert)
        .filter(Patient.status == "admitted", Alert.status == "active")
        .distinct()
        .count()
    )

    return {
        "active_patients": active_patients,
        "pending_tasks": pending_tasks,
        "completed_today": completed_today,
        "urgent_alerts": urgent_alerts,
        "attention_count": max(attention_count, urgent_alerts),
    }


@router.get("/clinician/analytics/overview")
def clinician_analytics_overview(db: Session = Depends(get_db)):
    """Macro inpatient health risk distribution and ANNA robot monitoring metrics."""
    # 1. Patient Risk Distribution
    active_patients = db.query(Patient).filter(Patient.status == "admitted").all()
    risk_counts = {"NORMAL": 0, "WARNING": 0, "URGENT": 0}
    for p in active_patients:
        r = calculate_risk(p, db)
        risk_counts[r] = risk_counts.get(r, 0) + 1

    # 2. ANNA Robot Fleet / Task Distribution
    total_tasks = db.query(RobotTask).count()
    completed_tasks = db.query(RobotTask).filter(RobotTask.status == "completed").count()
    pending_tasks = db.query(RobotTask).filter(RobotTask.status.in_(["queued", "in_progress"])).count()
    failed_tasks = db.query(RobotTask).filter(RobotTask.status == "failed").count()

    # 3. Last 7 Days ANNA Checkups
    now = dt.datetime.utcnow()
    day_labels = []
    daily_checkups = []
    for i in range(6, -1, -1):
        day_start = (now - dt.timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + dt.timedelta(days=1)
        day_labels.append(day_start.strftime("%a %d"))
        cnt = db.query(HealthCheckSession).filter(
            HealthCheckSession.completed_at >= day_start,
            HealthCheckSession.completed_at < day_end
        ).count()
        daily_checkups.append(cnt)

    return {
        "risk_distribution": risk_counts,
        "robot_fleet": {
            "total_tasks": total_tasks,
            "completed": completed_tasks,
            "pending": pending_tasks,
            "failed": failed_tasks,
        },
        "checkups_trend": {
            "labels": day_labels,
            "counts": daily_checkups,
        }
    }


@router.get("/patients")
def list_patients(
    query: str = "",
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    stmt = db.query(Patient).order_by(Patient.status.asc(), Patient.admission_date.desc())
    if active_only:
        stmt = stmt.filter(Patient.status == "admitted")
    if query.strip():
        term = f"%{query.strip()}%"
        stmt = stmt.filter(
            (Patient.patient_code.ilike(term))
            | (Patient.full_name.ilike(term))
            | (Patient.phone.ilike(term))
        )

    patients = stmt.all()
    results = []
    for p in patients:
        latest_vital = (
            db.query(VitalReading)
            .filter(VitalReading.patient_id == p.id)
            .order_by(VitalReading.recorded_at.desc())
            .first()
        )
        latest_emotion = (
            db.query(EmotionRecord)
            .filter(EmotionRecord.patient_id == p.id)
            .order_by(EmotionRecord.detected_at.desc())
            .first()
        )

        vitals_data = None
        if latest_vital:
            vitals_data = {
                "temperature": f"{latest_vital.temperature_c} °C",
                "pulse": f"{int(latest_vital.pulse_bpm)} BPM",
                "spo2": f"{latest_vital.spo2_percent}%",
                "ecg": latest_vital.ecg_note or "Sinus Rhythm",
                "emotion": latest_emotion.emotion if latest_emotion else "Neutral",
                "recorded_at": latest_vital.recorded_at.isoformat(),
            }

        risk = calculate_risk(p, db)
        results.append(
            {
                "id": p.id,
                "patient_code": p.patient_code,
                "full_name": p.full_name,
                "gender": p.gender,
                "blood_group": p.blood_group,
                "bed_number": p.bed_number,
                "admission_date": p.admission_date,
                "discharge_date": p.discharge_date,
                "status": p.status,
                "latest_vitals": vitals_data,
                "risk_level": risk,
            }
        )
    return results


@router.get("/patients/{patient_code}")
def get_patient_profile(patient_code: str, db: Session = Depends(get_db)):
    patient = (
        db.query(Patient)
        .filter(Patient.patient_code == patient_code.strip().upper())
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient record not found.")

    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "full_name": patient.full_name,
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender,
        "blood_group": patient.blood_group,
        "height_cm": patient.height_cm,
        "weight_kg": patient.weight_kg,
        "phone": patient.phone,
        "emergency_contact": patient.emergency_contact,
        "address": patient.address,
        "bed_number": patient.bed_number,
        "admission_date": patient.admission_date,
        "discharge_date": patient.discharge_date,
        "status": patient.status,
        "portal_pin": patient.portal_pin,
        "risk_level": calculate_risk(patient, db),
    }


@router.get("/patients/{patient_code}/analytics")
def get_patient_analytics(
    patient_code: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    patient = (
        db.query(Patient)
        .filter(Patient.patient_code == patient_code.strip().upper())
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    since_date = dt.datetime.utcnow() - dt.timedelta(days=days)

    # 1. Vital Time Series
    vitals_records = (
        db.query(VitalReading)
        .filter(VitalReading.patient_id == patient.id, VitalReading.recorded_at >= since_date)
        .order_by(VitalReading.recorded_at.asc())
        .all()
    )
    vitals_series = [
        {
            "timestamp": v.recorded_at.strftime("%b %d, %H:%M"),
            "temperature_c": v.temperature_c,
            "pulse_bpm": v.pulse_bpm,
            "spo2_percent": v.spo2_percent,
            "ecg_note": v.ecg_note or "Normal Sinus Rhythm",
            "quality": v.quality_status,
        }
        for v in vitals_records
    ]

    # 2. Emotion Breakdown
    emotions_query = (
        db.query(EmotionRecord.emotion, func.count(EmotionRecord.id))
        .filter(EmotionRecord.patient_id == patient.id, EmotionRecord.detected_at >= since_date)
        .group_by(EmotionRecord.emotion)
        .all()
    )
    emotion_distribution = {emo: count for emo, count in emotions_query}

    # 3. Wellness Responses
    responses_query = (
        db.query(PatientResponse)
        .filter(PatientResponse.patient_id == patient.id)
        .order_by(PatientResponse.created_at.desc())
        .limit(18)
        .all()
    )
    wellness_responses = [
        {"question": r.question, "answer": r.answer, "date": r.created_at.strftime("%b %d, %H:%M")}
        for r in responses_query
    ]

    # 4. Medical Summaries
    summaries = (
        db.query(MedicalSummary)
        .filter(MedicalSummary.patient_id == patient.id)
        .order_by(MedicalSummary.created_at.desc())
        .all()
    )
    summary_history = [
        {
            "id": s.id,
            "author": s.author,
            "clinical_summary": s.clinical_summary,
            "patient_summary": s.patient_summary,
            "temperature_c": s.temperature_c,
            "pulse_bpm": s.pulse_bpm,
            "spo2_percent": s.spo2_percent,
            "ecg_note": s.ecg_note,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for s in summaries
    ]

    # 5. Medications
    meds = db.query(Medication).filter(Medication.patient_id == patient.id).all()
    medications_list = [
        {
            "id": m.id,
            "medicine_name": m.medicine_name,
            "dosage": m.dosage,
            "frequency": m.frequency,
            "scheduled_time": m.scheduled_time,
            "instructions": m.instructions,
            "status": m.status,
        }
        for m in meds
    ]

    # 6. Alerts
    alerts = (
        db.query(Alert)
        .filter(Alert.patient_id == patient.id)
        .order_by(Alert.created_at.desc())
        .all()
    )
    alerts_list = [
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "status": a.status,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M"),
            "acknowledged_at": a.acknowledged_at.strftime("%Y-%m-%d %H:%M") if a.acknowledged_at else None,
            "acknowledged_by": a.acknowledged_by,
        }
        for a in alerts
    ]

    return {
        "patient": {
            "id": patient.id,
            "patient_code": patient.patient_code,
            "full_name": patient.full_name,
            "gender": patient.gender,
            "blood_group": patient.blood_group,
            "bed_number": patient.bed_number,
            "risk_level": calculate_risk(patient, db),
        },
        "vitals_series": vitals_series,
        "emotion_distribution": emotion_distribution,
        "wellness_responses": wellness_responses,
        "summaries": summary_history,
        "medications": medications_list,
        "alerts": alerts_list,
    }


# Tasks Management
@router.get("/tasks", response_model=List[TaskResponseModel])
def get_tasks(db: Session = Depends(get_db)):
    rows = (
        db.query(RobotTask, Patient)
        .join(Patient)
        .order_by(
            case((RobotTask.status == "in_progress", 0), (RobotTask.status == "queued", 1), else_=2),
            case((RobotTask.priority == "urgent", 0), else_=1),
            RobotTask.assigned_at.desc(),
        )
        .all()
    )
    return [
        TaskResponseModel(
            id=task.id,
            patient_code=p.patient_code,
            patient_name=p.full_name,
            bed_number=p.bed_number,
            task_type=task.task_type,
            instructions=task.instructions,
            priority=task.priority,
            status=task.status,
            assigned_by=task.assigned_by,
            assigned_at=task.assigned_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            failure_reason=task.failure_reason,
        )
        for task, p in rows
    ]


@router.post("/tasks", response_model=TaskResponseModel)
async def create_task(
    payload: TaskCreateRequest,
    request: Request = None,
    db: Session = Depends(get_db),
):
    patient = (
        db.query(Patient)
        .filter(Patient.patient_code == payload.patient_code.strip().upper(), Patient.status == "admitted")
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="The selected patient is not currently admitted.")

    assigner = "Dr. Sarah Rao, MD"
    if request and request.session.get("user_name"):
        assigner = request.session.get("user_name")

    task = RobotTask(
        patient_id=patient.id,
        task_type=payload.task_type,
        instructions=payload.instructions.strip(),
        priority=payload.priority,
        status="queued",
        assigned_by=assigner,
        assigned_at=dt.datetime.utcnow(),
    )
    db.add(task)

    db.add(
        AuditLog(
            user_id=request.session.get("user_id") if request else None,
            action="task_assignment",
            details=f"Assigned {payload.priority} task '{payload.task_type}' for {patient.full_name} ({patient.patient_code})",
            timestamp=dt.datetime.utcnow(),
            ip_address=request.client.host if request and request.client else "127.0.0.1",
        )
    )
    db.commit()
    db.refresh(task)

    # Broadcast event
    await ws_manager.broadcast(
        "task_created",
        {
            "task_id": task.id,
            "patient_code": patient.patient_code,
            "patient_name": patient.full_name,
            "bed_number": patient.bed_number,
            "priority": task.priority,
            "status": task.status,
        },
    )

    return TaskResponseModel(
        id=task.id,
        patient_code=patient.patient_code,
        patient_name=patient.full_name,
        bed_number=patient.bed_number,
        task_type=task.task_type,
        instructions=task.instructions,
        priority=task.priority,
        status=task.status,
        assigned_by=task.assigned_by,
        assigned_at=task.assigned_at,
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(RobotTask).filter(RobotTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel an already completed task.")

    task.status = "cancelled"
    task.completed_at = dt.datetime.utcnow()
    db.commit()

    await ws_manager.broadcast("task_updated", {"task_id": task.id, "status": "cancelled"})
    return {"ok": True, "task_id": task.id, "status": "cancelled"}


# Alert Center
@router.get("/alerts", response_model=List[AlertResponseModel])
def list_alerts(status: str = "active", db: Session = Depends(get_db)):
    query = db.query(Alert, Patient).join(Patient)
    if status != "all":
        query = query.filter(Alert.status == status)

    query = query.order_by(
        case((Alert.severity == "URGENT", 0), (Alert.severity == "WARNING", 1), else_=2),
        Alert.created_at.desc(),
    )
    rows = query.all()

    return [
        AlertResponseModel(
            id=a.id,
            patient_id=p.id,
            patient_code=p.patient_code,
            patient_name=p.full_name,
            bed_number=p.bed_number,
            alert_type=a.alert_type,
            severity=a.severity,
            message=a.message,
            status=a.status,
            created_at=a.created_at,
            acknowledged_at=a.acknowledged_at,
            acknowledged_by=a.acknowledged_by,
        )
        for a, p in rows
    ]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    payload: AlertAcknowledgeRequest,
    request: Request = None,
    db: Session = Depends(get_db),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    doctor_name = "Dr. Sarah Rao, MD"
    if request and request.session.get("user_name"):
        doctor_name = request.session.get("user_name")

    alert.status = "acknowledged"
    alert.acknowledged_at = dt.datetime.utcnow()
    alert.acknowledged_by = doctor_name
    if payload.note:
        alert.message += f" [Clinical Note: {payload.note.strip()}]"

    db.add(
        AuditLog(
            user_id=request.session.get("user_id") if request else None,
            action="alert_acknowledge",
            details=f"Alert #{alert.id} acknowledged by {doctor_name}.",
            timestamp=dt.datetime.utcnow(),
            ip_address=request.client.host if request and request.client else "127.0.0.1",
        )
    )
    db.commit()

    await ws_manager.broadcast("alert_acknowledged", {"alert_id": alert.id, "acknowledged_by": doctor_name})
    return {"ok": True, "alert_id": alert.id, "status": "acknowledged"}


# Patient Portal PIN Reset
@router.post("/patients/{patient_code}/portal-pin")
def reset_patient_portal_pin(patient_code: str, db: Session = Depends(get_db)):
    patient = (
        db.query(Patient)
        .filter(Patient.patient_code == patient_code.strip().upper())
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    new_pin = f"{secrets.randbelow(1_000_000):06d}"
    patient.portal_pin = new_pin
    patient.portal_pin_hash = hash_password(new_pin)
    db.commit()

    return {"patient_code": patient.patient_code, "portal_pin": new_pin}


# Prescribe Medication
@router.post("/patients/{patient_code}/medications")
def prescribe_medication(
    patient_code: str,
    payload: MedicationCreateRequest,
    db: Session = Depends(get_db),
):
    patient = (
        db.query(Patient)
        .filter(Patient.patient_code == patient_code.strip().upper())
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    med = Medication(
        patient_id=patient.id,
        medicine_name=payload.medicine_name.strip(),
        dosage=payload.dosage.strip(),
        frequency=payload.frequency.strip(),
        scheduled_time=payload.scheduled_time.strip(),
        instructions=payload.instructions.strip(),
        status="active",
    )
    db.add(med)
    db.commit()
    db.refresh(med)

    return {"ok": True, "medication_id": med.id, "medicine_name": med.medicine_name}


# Summaries
@router.get("/summaries")
def get_summaries(patient_code: Optional[str] = None, db: Session = Depends(get_db)):
    query = (
        db.query(MedicalSummary, Patient)
        .join(Patient)
        .order_by(MedicalSummary.created_at.desc())
    )
    if patient_code:
        query = query.filter(Patient.patient_code == patient_code.strip().upper())

    rows = query.all()
    return [
        {
            "id": s.id,
            "patient_code": p.patient_code,
            "patient_name": p.full_name,
            "bed_number": p.bed_number,
            "author": s.author,
            "clinical_summary": s.clinical_summary,
            "patient_summary": s.patient_summary,
            "temperature_c": s.temperature_c,
            "pulse_bpm": s.pulse_bpm,
            "spo2_percent": s.spo2_percent,
            "ecg_note": s.ecg_note,
            "created_at": s.created_at,
        }
        for s, p in rows
    ]
