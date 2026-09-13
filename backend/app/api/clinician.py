"""Clinician Dashboard API routes: patient analytics, task orchestration, alerts."""

from __future__ import annotations

import datetime as dt
import logging
import secrets
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
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
    User,
)
from ..auth import get_current_user, hash_password, require_role
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
from ..services.patient_attention import assess_patient, patient_contexts
from ..services.measurements import display

logger = logging.getLogger("anna.clinician")
router = APIRouter(prefix="/api", tags=["clinician"], dependencies=[Depends(require_role("doctor", "nurse", "admin"))])


def calculate_risk(patient: Patient, db: Session) -> str:
    return assess_patient(db, patient)["level"]


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
        .filter(Alert.status.in_(["active", "new"]), Alert.severity.in_(["URGENT", "CRITICAL"]))
        .count()
    )

    # Patients needing attention (abnormal vitals or active alerts)
    attention_count = (
        db.query(Patient.id)
        .join(Alert)
        .filter(Patient.status == "admitted", Alert.status.in_(["active", "new", "under_review"]))
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
    readings_by_patient, alerts_by_patient = patient_contexts(db, [p.id for p in active_patients])
    risk_counts = {"STABLE": 0, "OBSERVE": 0, "REVIEW": 0, "URGENT": 0, "CRITICAL": 0}
    for p in active_patients:
        r = assess_patient(db, p, readings=readings_by_patient[p.id], alerts=alerts_by_patient[p.id])["level"]
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
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = db.query(Patient).order_by(Patient.status.asc(), Patient.admission_date.desc())
    if active_only:
        stmt = stmt.filter(Patient.status == "admitted")
    if query.strip():
        term = f"%{query.strip()}%"
        criteria = (Patient.patient_code.ilike(term)) | (Patient.full_name.ilike(term)) | (Patient.phone.ilike(term))
        if query.strip().isdigit():
            criteria = criteria | (Patient.bed_number == int(query.strip()))
        stmt = stmt.filter(criteria)

    total = stmt.count() if page is not None else None
    patients = stmt.offset((page - 1) * page_size).limit(page_size).all() if page is not None else stmt.all()
    results = []
    readings_by_patient, alerts_by_patient = patient_contexts(db, [p.id for p in patients])
    patient_ids = [p.id for p in patients]
    emotion_by_patient = {}
    if patient_ids:
        ranked_emotions = db.query(EmotionRecord.id.label("id"), func.row_number().over(
            partition_by=EmotionRecord.patient_id,
            order_by=(EmotionRecord.detected_at.desc(), EmotionRecord.id.desc())).label("position")
        ).filter(EmotionRecord.patient_id.in_(patient_ids)).subquery()
        emotion_by_patient = {emotion.patient_id: emotion for emotion in db.query(EmotionRecord).join(
            ranked_emotions, ranked_emotions.c.id == EmotionRecord.id).filter(ranked_emotions.c.position == 1).all()}
    for p in patients:
        latest_vital = next((v for v in readings_by_patient[p.id] if v.quality_status != "simulated"), None)
        latest_emotion = emotion_by_patient.get(p.id)

        vitals_data = None
        if latest_vital:
            vitals_data = {
                "temperature": display(latest_vital.temperature_c, '°C') if latest_vital.temperature_status == "measured" else "Unavailable",
                "pulse": display(latest_vital.pulse_bpm, 'BPM') if latest_vital.pulse_status == "measured" else "Unavailable",
                "spo2": display(latest_vital.spo2_percent, '%') if latest_vital.spo2_status == "measured" else "Unavailable",
                "ecg": latest_vital.ecg_note or "Not available",
                "emotion": latest_emotion.emotion if latest_emotion else "Not available",
                "recorded_at": latest_vital.recorded_at.isoformat(),
                "source": latest_vital.source,
                "quality_status": latest_vital.quality_status,
            }

        attention = assess_patient(db, p, readings=readings_by_patient[p.id], alerts=alerts_by_patient[p.id])
        risk = attention["level"]
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
                "attention": attention,
            }
        )
    if page is not None:
        return {"items": results, "total": total, "page": page, "page_size": page_size,
                "pages": (total + page_size - 1) // page_size}
    return results


@router.get("/clinician/patient-options")
def patient_options(db: Session = Depends(get_db)):
    rows = db.query(Patient.patient_code, Patient.full_name, Patient.bed_number).filter(
        Patient.status == "admitted").order_by(Patient.full_name).all()
    return [{"patient_code": code, "full_name": name, "bed_number": bed} for code, name, bed in rows]


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
        "date_of_birth": patient.birth_date.isoformat() if patient.birth_date else patient.date_of_birth,
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
        "risk_level": calculate_risk(patient, db),
        "attention": assess_patient(db, patient),
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
            "ecg_note": v.ecg_note or "Not available",
            "temperature_status": v.temperature_status,
            "pulse_status": v.pulse_status,
            "spo2_status": v.spo2_status,
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
@router.get("/tasks")
def get_tasks(page: int | None = Query(default=None, ge=1),
              page_size: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    query = (
        db.query(RobotTask, Patient)
        .join(Patient)
        .order_by(
            case((RobotTask.status == "in_progress", 0), (RobotTask.status == "queued", 1), else_=2),
            case((RobotTask.priority == "urgent", 0), else_=1),
            RobotTask.assigned_at.desc(),
        )
    )
    total = query.count() if page is not None else None
    rows = query.offset((page - 1) * page_size).limit(page_size).all() if page is not None else query.all()
    results = [
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
            robot_id=task.robot_id,
            current_stage=task.current_stage,
            stage_updated_at=task.stage_updated_at,
        )
        for task, p in rows
    ]
    if page is not None:
        return {"items": results, "total": total, "page": page, "page_size": page_size,
                "pages": (total + page_size - 1) // page_size}
    return results


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

    assigner = "Clinical user"
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
@router.get("/alerts")
def list_alerts(status: str = "active", page: int | None = Query(default=None, ge=1),
                page_size: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    query = db.query(Alert, Patient).join(Patient)
    if status == "active":
        query = query.filter(Alert.status.in_(["active", "new", "under_review"]))
    elif status != "all":
        query = query.filter(Alert.status == status)

    query = query.order_by(
        case((Alert.severity == "URGENT", 0), (Alert.severity == "WARNING", 1), else_=2),
        Alert.created_at.desc(),
    )
    total = query.count() if page is not None else None
    rows = query.offset((page - 1) * page_size).limit(page_size).all() if page is not None else query.all()

    results = [
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
            metric=a.metric,
            actual_value=a.actual_value,
            threshold_value=a.threshold_value,
            previous_value=a.previous_value,
            delta=a.delta,
            source=a.source,
            resolved_at=a.resolved_at,
            resolved_by=a.resolved_by,
        )
        for a, p in rows
    ]
    if page is not None:
        return {"items": results, "total": total, "page": page, "page_size": page_size,
                "pages": (total + page_size - 1) // page_size}
    return results


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
    if alert.status not in {"active", "new", "under_review"}:
        raise HTTPException(status_code=409, detail="Alert has already been handled.")

    doctor_name = "Clinical user"
    if request and request.session.get("user_name"):
        doctor_name = request.session.get("user_name")

    alert.status = "acknowledged"
    alert.acknowledged_at = dt.datetime.utcnow()
    alert.acknowledged_by = doctor_name
    if payload.note:
        alert.resolution_note = payload.note.strip()

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
def reset_patient_portal_pin(patient_code: str, response: Response,
                             user: User = Depends(require_role("doctor", "admin")),
                             db: Session = Depends(get_db)):
    patient = (
        db.query(Patient)
        .filter(Patient.patient_code == patient_code.strip().upper())
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    new_pin = f"{secrets.randbelow(1_000_000):06d}"
    patient.portal_pin = None
    patient.portal_pin_hash = hash_password(new_pin)
    db.add(AuditLog(user_id=user.id, actor_role=user.role, action="portal_pin_reset",
                    entity_type="patient", entity_id=patient.patient_code, source="web",
                    details=f"Portal PIN reset for {patient.patient_code}.", timestamp=dt.datetime.utcnow()))
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"patient_code": patient.patient_code, "portal_pin": new_pin}


# Prescribe Medication
@router.post("/patients/{patient_code}/medications")
def prescribe_medication(
    patient_code: str,
    payload: MedicationCreateRequest,
    user: User = Depends(require_role("doctor", "admin")),
    db: Session = Depends(get_db),
):
    patient = (
        db.query(Patient)
        .filter(Patient.patient_code == patient_code.strip().upper())
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    if patient.status != "admitted":
        raise HTTPException(status_code=409, detail="Medication changes require an admitted patient.")
    if not payload.medicine_name.strip() or not payload.dosage.strip() or not payload.frequency.strip():
        raise HTTPException(status_code=422, detail="Medicine, dose and frequency are required.")

    times = payload.schedule_times if payload.schedule_times is not None else [part.strip() for part in payload.scheduled_time.split(",")]
    if not times or len(times) > 12 or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", part) for part in times):
        raise HTTPException(status_code=422, detail="Provide valid 24-hour medication times (HH:MM).")
    med = Medication(
        patient_id=patient.id,
        medicine_name=payload.medicine_name.strip(),
        dosage=payload.dosage.strip(),
        frequency=payload.frequency.strip(),
        scheduled_time=", ".join(times),
        schedule_times=times,
        prescriber_id=user.id,
        created_at=dt.datetime.utcnow(),
        instructions=payload.instructions.strip(),
        status="active",
    )
    db.add(med)
    db.flush()
    db.add(AuditLog(user_id=user.id, actor_role=user.role, action="medication_prescribed",
                    entity_type="medication", entity_id=str(med.id), source="web",
                    details=f"Medication prescribed for {patient.patient_code}.", timestamp=dt.datetime.utcnow()))
    db.commit()
    db.refresh(med)

    return {"ok": True, "medication_id": med.id, "medicine_name": med.medicine_name}


@router.post("/patients/{patient_code}/medications/{medication_id}/discontinue")
def discontinue_medication(patient_code: str, medication_id: int,
                           user: User = Depends(require_role("doctor", "admin")),
                           db: Session = Depends(get_db)):
    medication = db.query(Medication).join(Patient).filter(
        Medication.id == medication_id, Patient.patient_code == patient_code.strip().upper()).first()
    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found for this patient.")
    if medication.status != "active":
        raise HTTPException(status_code=409, detail="Medication is already inactive.")
    medication.status = "discontinued"
    medication.end_date = dt.datetime.utcnow()
    db.add(AuditLog(user_id=user.id, actor_role=user.role, action="medication_discontinued",
                    entity_type="medication", entity_id=str(medication.id), source="web",
                    details=f"Medication discontinued for {patient_code.upper()}.", timestamp=dt.datetime.utcnow()))
    db.commit()
    return {"ok": True, "status": medication.status}


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
    session_ids = [s.session_id for s, _ in rows if s.session_id is not None]
    quality_by_session = {}
    if session_ids:
        for vital in db.query(VitalReading).filter(VitalReading.session_id.in_(session_ids)).all():
            quality_by_session[vital.session_id] = vital.quality_status
    return [
        {
            "id": s.id,
            "patient_code": p.patient_code,
            "patient_name": p.full_name,
            "bed_number": p.bed_number,
            "author": s.author,
            "quality_status": quality_by_session.get(s.session_id) if s.session_id is not None else None,
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
