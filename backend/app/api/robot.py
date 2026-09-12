"""ANNA Robot controller integration & live SIH checkup simulation endpoints."""

from __future__ import annotations

import datetime as dt
import logging
import random
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import case
from sqlalchemy.orm import Session

from dashboards.common.database import get_db
from dashboards.common.models import (
    Alert,
    AuditLog,
    EmotionRecord,
    HealthCheckSession,
    MedicalSummary,
    Patient,
    PatientResponse,
    RobotTask,
    VitalReading,
)
from ..auth import robot_authorised
from ..schemas import RobotCompleteRequest, TaskResponseModel
from ..websocket import ws_manager

logger = logging.getLogger("anna.robot")
router = APIRouter(prefix="/api/robot", tags=["robot"])


@router.post("/tasks/next", response_model=TaskResponseModel)
async def claim_next_task(
    _: None = Depends(robot_authorised),
    db: Session = Depends(get_db),
):
    """Robot claims next queued task with priority."""
    task = (
        db.query(RobotTask)
        .filter(RobotTask.status == "queued")
        .order_by(
            case((RobotTask.priority == "urgent", 0), else_=1),
            RobotTask.assigned_at.asc(),
        )
        .with_for_update()
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="No queued tasks available.")

    patient = db.get(Patient, task.patient_id)
    task.status = "in_progress"
    task.started_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(task)

    # Broadcast event
    await ws_manager.broadcast(
        "task_updated",
        {
            "task_id": task.id,
            "patient_code": patient.patient_code,
            "status": "in_progress",
            "started_at": task.started_at.isoformat(),
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
        started_at=task.started_at,
    )


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: int,
    payload: RobotCompleteRequest,
    _: None = Depends(robot_authorised),
    db: Session = Depends(get_db),
):
    """Robot posts completed vitals, summaries, and responses."""
    task = db.get(RobotTask, task_id)
    if not task or task.status != "in_progress":
        raise HTTPException(status_code=409, detail="Task is not active or in progress.")

    patient = db.get(Patient, task.patient_id)
    task.status = payload.status
    task.completed_at = dt.datetime.utcnow()
    task.failure_reason = payload.failure_reason

    if payload.status == "completed":
        # 1. Create Health Check Session
        session = HealthCheckSession(
            patient_id=patient.id,
            robot_task_id=task.id,
            started_at=task.started_at or dt.datetime.utcnow(),
            completed_at=task.completed_at,
            status="completed",
        )
        db.add(session)
        db.flush()

        # 2. Parse vitals
        try:
            temp_num = float(str(payload.temperature_c or "36.8").replace("C", "").strip())
        except ValueError:
            temp_num = 36.8

        try:
            pulse_num = float(str(payload.pulse_bpm or "75").replace("BPM", "").strip())
        except ValueError:
            pulse_num = 75.0

        try:
            spo2_num = float(str(payload.spo2_percent or "98.0").replace("%", "").strip())
        except ValueError:
            spo2_num = 98.0

        vital = VitalReading(
            session_id=session.id,
            patient_id=patient.id,
            temperature_c=temp_num,
            pulse_bpm=pulse_num,
            spo2_percent=spo2_num,
            ecg_value="0.92 mV",
            ecg_note=payload.ecg_note or "Normal Sinus Rhythm",
            recorded_at=dt.datetime.utcnow(),
            source="ANNA Robot",
            quality_status="measured",
        )
        db.add(vital)

        # 3. Store Emotion
        emo = payload.emotion or "Neutral"
        db.add(
            EmotionRecord(
                session_id=session.id,
                patient_id=patient.id,
                emotion=emo,
                confidence=0.96,
                detected_at=dt.datetime.utcnow(),
            )
        )

        # 4. Store Questionnaire answers
        if payload.answers:
            for q, a in payload.answers.items():
                db.add(
                    PatientResponse(
                        session_id=session.id,
                        patient_id=patient.id,
                        question=str(q),
                        answer=str(a),
                        created_at=dt.datetime.utcnow(),
                    )
                )

        # 5. Dual Summaries
        clinical_text = payload.clinical_summary or payload.summary or (
            f"ANNA bedside assessment completed. Temperature: {temp_num}°C; "
            f"Pulse: {pulse_num} BPM (simulated); SpO2: {spo2_num}%; ECG: {payload.ecg_note}. "
            "Requires clinician review; prototype readings are not diagnostic."
        )
        patient_text = payload.patient_summary or (
            f"Hello {patient.full_name.split()[0]}! ANNA has recorded your check-in information "
            f"(Temperature: {temp_num}°C, Heart Rate: {int(pulse_num)} BPM). "
            "Your care team has received your update. Please rest comfortably!"
        )

        db.add(
            MedicalSummary(
                patient_id=patient.id,
                task_id=task.id,
                session_id=session.id,
                author="ANNA Robot",
                clinical_summary=clinical_text,
                patient_summary=patient_text,
                temperature_c=f"{temp_num} C",
                pulse_bpm=f"{int(pulse_num)} BPM",
                spo2_percent=f"{spo2_num}%",
                ecg_note=payload.ecg_note,
                created_at=dt.datetime.utcnow(),
            )
        )

        # 6. Automatic Alert Trigger if abnormal
        if temp_num >= 38.0:
            db.add(
                Alert(
                    patient_id=patient.id,
                    session_id=session.id,
                    alert_type="Vital Threshold",
                    severity="URGENT",
                    message=f"Elevated temperature detected: {temp_num}°C. Clinician evaluation advised.",
                    created_at=dt.datetime.utcnow(),
                    status="active",
                )
            )
        elif pulse_num >= 105 or spo2_num < 94.0:
            db.add(
                Alert(
                    patient_id=patient.id,
                    session_id=session.id,
                    alert_type="Vital Threshold",
                    severity="WARNING",
                    message=f"Abnormal vitals detected: Pulse {int(pulse_num)} BPM, SpO2 {spo2_num}%.",
                    created_at=dt.datetime.utcnow(),
                    status="active",
                )
            )

    db.add(
        AuditLog(
            user_id=None,
            action="health_record_creation",
            details=f"ANNA completed checkup task #{task.id} for {patient.full_name} ({patient.patient_code}).",
            timestamp=dt.datetime.utcnow(),
            ip_address="127.0.0.1",
        )
    )
    db.commit()

    # Broadcast real-time checkup completion
    await ws_manager.broadcast(
        "checkup_completed",
        {
            "task_id": task.id,
            "patient_code": patient.patient_code,
            "patient_name": patient.full_name,
            "bed_number": patient.bed_number,
            "temperature": f"{temp_num} °C",
            "pulse": f"{int(pulse_num)} BPM",
            "spo2": f"{spo2_num}%",
            "ecg": payload.ecg_note or "Normal Sinus Rhythm",
        },
    )

    return {"ok": True, "return_to_home": True}


# SIH 2026 Live Demo Simulation Endpoint
@router.post("/simulate-checkup/{task_id}")
async def simulate_checkup(task_id: int, db: Session = Depends(get_db)):
    """Allows doctors to trigger a live simulation of ANNA performing the checkup for demonstration."""
    task = db.get(RobotTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    patient = db.get(Patient, task.patient_id)
    task.status = "in_progress"
    task.started_at = dt.datetime.utcnow()
    db.commit()

    # Generate realistic checkup payload
    t_val = round(random.uniform(36.4, 37.6), 1)
    p_val = random.randint(68, 86)
    spo2_val = round(random.uniform(96.5, 99.0), 1)
    emotions = ["Happy", "Neutral", "Neutral", "Surprise"]
    emo = random.choice(emotions)
    ecg_options = ["Normal Sinus Rhythm", "Normal Sinus Rhythm", "Slightly Irregular"]
    ecg_note = random.choice(ecg_options)

    answers = {
        "Sleep Hours": f"{random.randint(6, 8)} hours",
        "Water Intake": f"{random.randint(5, 8)} glasses",
        "Pain/Discomfort": "None reported",
        "Appetite": "Normal",
        "Exercise Today": "Short ward walk",
        "Stress Level": str(random.randint(2, 5)),
    }

    clinical_sum = (
        f"Simulated ANNA checkup completed on {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}. "
        f"Temperature: {t_val}°C; Pulse: {p_val} BPM; SpO2: {spo2_val}%; ECG: {ecg_note}. "
        f"Facial affect: {emo}. Patient reported normal appetite and adequate hydration. "
        "Requires clinician review; prototype readings are not diagnostic."
    )
    patient_sum = (
        f"Hello {patient.full_name.split()[0]}! ANNA completed your health checkup. "
        f"Your temperature was {t_val}°C, pulse was {p_val} BPM, and oxygen saturation was {spo2_val}%. "
        f"It was nice to see you looking {emo.lower()} today! All vitals have been saved to your health chart."
    )

    req = RobotCompleteRequest(
        status="completed",
        temperature_c=f"{t_val} C",
        pulse_bpm=f"{p_val} BPM",
        spo2_percent=f"{spo2_val}%",
        ecg_note=ecg_note,
        emotion=emo,
        answers=answers,
        clinical_summary=clinical_sum,
        patient_summary=patient_sum,
    )

    return await complete_task(task_id=task.id, payload=req, _=None, db=db)
