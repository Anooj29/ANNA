"""ANNA Robot controller integration & live SIH checkup simulation endpoints."""

from __future__ import annotations

import datetime as dt
import logging
import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case
from sqlalchemy.orm import Session

from dashboards.common.config import config
from dashboards.common.database import get_db
from dashboards.common.models import (
    AuditLog,
    EmotionRecord,
    HealthCheckSession,
    MedicalSummary,
    Patient,
    PatientResponse,
    RobotTask,
    RobotStatus,
    VitalReading,
)
from ..auth import robot_authorised, require_role
from ..schemas import RobotCompleteRequest, RobotHeartbeatRequest, RobotProgressRequest, TaskResponseModel
from ..websocket import ws_manager
from ..services.measurements import parse_measurement, display
from ..services.alerts import create_vital_alerts
from ..services.notifications import notify_clinicians

logger = logging.getLogger("anna.robot")
router = APIRouter(prefix="/api/robot", tags=["robot"])


@router.post("/tasks/next", response_model=TaskResponseModel)
async def claim_next_task(
    robot_id: Optional[str] = None,
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
        .with_for_update(skip_locked=True)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="No queued tasks available.")

    patient = db.get(Patient, task.patient_id)
    task.status = "in_progress"
    task.started_at = dt.datetime.utcnow()
    if robot_id:
        task.robot_id = robot_id
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


@router.post("/heartbeat")
async def heartbeat(payload: RobotHeartbeatRequest, _: None = Depends(robot_authorised), db: Session = Depends(get_db)):
    robot = db.query(RobotStatus).filter(RobotStatus.robot_id == payload.robot_id).first()
    if robot is None:
        robot = RobotStatus(robot_id=payload.robot_id)
        db.add(robot)
    robot.last_seen_at = dt.datetime.utcnow()
    robot.status = payload.status
    robot.current_task_id = payload.current_task_id
    robot.battery_percent = payload.battery_percent
    robot.detail = payload.detail
    db.commit()
    await ws_manager.broadcast("robot_status_updated", {"robot_id": robot.robot_id, "status": robot.status,
                                                       "last_seen_at": robot.last_seen_at.isoformat()})
    return {"ok": True}


@router.post("/tasks/{task_id}/progress")
async def task_progress(task_id: int, payload: RobotProgressRequest,
                        _: None = Depends(robot_authorised), db: Session = Depends(get_db)):
    task = db.get(RobotTask, task_id)
    if not task or task.status != "in_progress":
        raise HTTPException(status_code=409, detail="Task is not active.")
    if task.robot_id and payload.robot_id and task.robot_id != payload.robot_id:
        raise HTTPException(status_code=403, detail="Task belongs to another robot.")
    task.current_stage = payload.stage
    task.stage_updated_at = dt.datetime.utcnow()
    if payload.robot_id:
        task.robot_id = payload.robot_id
    db.commit()
    await ws_manager.broadcast("task_updated", {"task_id": task.id, "status": task.status,
                                              "stage": task.current_stage, "robot_id": task.robot_id})
    return {"ok": True, "task_id": task.id, "stage": task.current_stage}

@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: int,
    payload: RobotCompleteRequest,
    _: None = Depends(robot_authorised),
    db: Session = Depends(get_db),
):
    return await _complete_task(task_id, payload, db)


async def _complete_task(task_id: int, payload: RobotCompleteRequest, db: Session, simulated: bool = False):
    """Robot posts completed vitals, summaries, and responses."""
    task = db.get(RobotTask, task_id)
    if not task or task.status != "in_progress":
        raise HTTPException(status_code=409, detail="Task is not active or in progress.")

    patient = db.get(Patient, task.patient_id)
    if payload.status == "completed":
        temperature = parse_measurement(payload.temperature_c, "C", 25, 45, payload.temperature_status, payload.temperature_quality, simulated)
        pulse = parse_measurement(payload.pulse_bpm, "BPM", 20, 250, payload.pulse_status, payload.pulse_quality, simulated)
        spo2 = parse_measurement(payload.spo2_percent, "%", 0, 100, payload.spo2_status, payload.spo2_quality, simulated)

    task.status = payload.status
    task.completed_at = dt.datetime.utcnow()
    task.failure_reason = payload.failure_reason
    if payload.robot_id:
        task.robot_id = payload.robot_id

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

        # 2. Store validated measurements.
        vital = VitalReading(
            session_id=session.id,
            patient_id=patient.id,
            temperature_c=temperature.value,
            pulse_bpm=pulse.value,
            spo2_percent=spo2.value,
            temperature_status=temperature.status,
            pulse_status=pulse.status,
            spo2_status=spo2.status,
            temperature_quality=temperature.quality,
            pulse_quality=pulse.quality,
            spo2_quality=spo2.quality,
            device_id=payload.robot_id,
            ecg_value=None,
            ecg_note=payload.ecg_note,
            recorded_at=dt.datetime.utcnow(),
            source="ANNA Robot",
            quality_status="simulated" if simulated else "measured" if any(m.status == "measured" for m in (temperature, pulse, spo2)) else "not_available",
        )
        db.add(vital)
        db.flush()

        # 3. Store Emotion
        if payload.emotion and payload.emotion_confidence is not None:
            db.add(EmotionRecord(
                session_id=session.id,
                patient_id=patient.id,
                emotion=payload.emotion,
                confidence=payload.emotion_confidence,
                detected_at=dt.datetime.utcnow(),
            ))

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
            f"ANNA bedside assessment completed. Temperature: {display(temperature.value, '°C')}; "
            f"Pulse: {display(pulse.value, 'BPM')}; SpO2: {display(spo2.value, '%')}; ECG: {payload.ecg_note or 'not available'}. "
            "Requires clinician review; prototype readings are not diagnostic."
        )
        patient_text = payload.patient_summary or (
            f"Hello {patient.full_name.split()[0]}! ANNA has recorded your check-in information "
            f"(Temperature: {display(temperature.value, '°C')}, Heart Rate: {display(pulse.value, 'BPM')}). "
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
                temperature_c=display(temperature.value, 'C') if temperature.status == "measured" else None,
                pulse_bpm=display(pulse.value, 'BPM') if pulse.status == "measured" else None,
                spo2_percent=display(spo2.value, '%') if spo2.status == "measured" else None,
                ecg_note=payload.ecg_note,
                created_at=dt.datetime.utcnow(),
            )
        )

        # Configured deterministic alerts use only reliable measured values.
        created_alerts = create_vital_alerts(db, vital)
        db.flush()
        for alert in created_alerts:
            notify_clinicians(db, event_type="alert", title=f"{alert.severity} · {patient.patient_code} · {alert.metric}",
                              patient_id=patient.id, alert_id=alert.id, task_id=task.id)
        if not simulated and any(m.status in {"poor_signal", "sensor_error", "invalid"} for m in (temperature, pulse, spo2)):
            notify_clinicians(db, event_type="measurement_quality", title=f"Measurement needs review · {patient.patient_code}",
                              patient_id=patient.id, task_id=task.id)

    if task.status == "failed":
        notify_clinicians(db, event_type="task_failed", title=f"ANNA visit failed · {patient.patient_code}",
                          patient_id=patient.id, task_id=task.id)

    db.add(
        AuditLog(
            user_id=None,
            action="health_record_creation",
            details=f"ANNA task #{task.id} ended with status {task.status} for patient {patient.patient_code}.",
            timestamp=dt.datetime.utcnow(),
            ip_address="127.0.0.1",
        )
    )
    db.commit()

    # Broadcast real-time checkup completion
    await ws_manager.broadcast(
        "checkup_completed" if task.status == "completed" else "task_updated",
        {
            "task_id": task.id,
            "patient_code": patient.patient_code,
            "patient_name": patient.full_name,
            "bed_number": patient.bed_number,
            "status": task.status,
            "quality_status": "simulated" if simulated else vital.quality_status if task.status == "completed" else "not_available",
            "temperature": display(temperature.value, '°C') if payload.status == "completed" else None,
            "pulse": display(pulse.value, 'BPM') if payload.status == "completed" else None,
            "spo2": display(spo2.value, '%') if payload.status == "completed" else None,
            "ecg": payload.ecg_note if payload.status == "completed" else None,
        },
    )
    if task.status == "completed" and created_alerts:
        await ws_manager.broadcast("alert_created", {"patient_code": patient.patient_code, "count": len(created_alerts)})

    return {"ok": True, "return_to_home": True}


# SIH 2026 Live Demo Simulation Endpoint
@router.post("/simulate-checkup/{task_id}")
async def simulate_checkup(task_id: int, _: None = Depends(require_role("doctor", "nurse", "admin")), db: Session = Depends(get_db)):
    """Allows doctors to trigger a live simulation of ANNA performing the checkup for demonstration."""
    if not config.enable_demo_simulation:
        raise HTTPException(status_code=403, detail="Demo simulation is disabled.")
    task = db.get(RobotTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status != "queued":
        raise HTTPException(status_code=409, detail="Only queued tasks can be simulated.")

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
        "This was a demonstration simulation, not a real health check. "
        "No clinical decisions should be made from these generated values."
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

    return await _complete_task(task.id, req, db, simulated=True)
