"""Clinician task, summary and telepresence dashboard.

The browser never talks to the robot directly. It places a visit in the
shared database; an authorised robot controller claims the next visit at
``/api/robot/tasks/next`` and posts a final summary when it returns home.
"""
from __future__ import annotations

import datetime as dt
import hmac
import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from ..common.config import config
from ..common.database import get_db
from ..common.models import MedicalSummary, Patient, RobotTask
from .schemas import LoginIn, PatientOut, RobotCompleteIn, SummaryOut, TaskIn, TaskOut

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app = FastAPI(title="ANNA - Clinician Dashboard")
app.add_middleware(SessionMiddleware, secret_key=config.session_secret, same_site="lax", https_only=False)


def clinician(request: Request) -> str:
    identity = request.session.get("clinician")
    if not identity:
        raise HTTPException(401, "Please sign in to access clinical records.")
    return str(identity)


def robot_authorised(x_anna_robot_key: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_anna_robot_key, config.robot_api_key):
        raise HTTPException(401, "Robot authorisation failed.")


def task_out(task: RobotTask, patient: Patient) -> dict:
    return {"id": task.id, "patient_code": patient.patient_code, "patient_name": patient.full_name,
            "bed_number": patient.bed_number, "task_type": task.task_type, "instructions": task.instructions,
            "priority": task.priority, "status": task.status, "assigned_by": task.assigned_by,
            "created_at": task.created_at, "started_at": task.started_at, "completed_at": task.completed_at,
            "failure_reason": task.failure_reason}


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request):
    if not (hmac.compare_digest(payload.email.strip().lower(), config.clinician_email)
            and hmac.compare_digest(payload.password, config.clinician_password)):
        raise HTTPException(401, "Incorrect email or password.")
    request.session["clinician"] = payload.email.strip().lower()
    return {"email": request.session["clinician"]}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    return {"email": request.session.get("clinician")}


@app.get("/api/patients", response_model=list[PatientOut])
def patients(query: str = "", active_only: bool = False, _: str = Depends(clinician), db: Session = Depends(get_db)):
    """Clinical search includes prior admissions; the task picker asks for active_only."""
    statement = select(Patient).order_by(Patient.discharged_at.is_(None).desc(), Patient.registered_at.desc())
    if active_only:
        statement = statement.where(Patient.discharged_at.is_(None))
    if query.strip():
        term = f"%{query.strip()}%"
        statement = statement.where((Patient.patient_code.ilike(term)) | (Patient.full_name.ilike(term)))
    return db.execute(statement).scalars().all()


@app.post("/api/patients/{patient_code}/portal-pin")
def reset_portal_pin(patient_code: str, _: str = Depends(clinician), db: Session = Depends(get_db)):
    patient = db.execute(select(Patient).where(Patient.patient_code == patient_code)).scalar_one_or_none()
    if patient is None:
        raise HTTPException(404, "Patient not found.")
    patient.portal_pin = f"{secrets.randbelow(1_000_000):06d}"
    db.commit()
    return {"patient_code": patient.patient_code, "portal_pin": patient.portal_pin}


@app.get("/api/tasks", response_model=list[TaskOut])
def tasks(_: str = Depends(clinician), db: Session = Depends(get_db)):
    rows = db.execute(select(RobotTask, Patient).join(Patient).order_by(RobotTask.created_at.desc())).all()
    return [task_out(task, patient) for task, patient in rows]


@app.post("/api/tasks", response_model=TaskOut)
def create_task(payload: TaskIn, identity: str = Depends(clinician), db: Session = Depends(get_db)):
    patient = db.execute(select(Patient).where(Patient.patient_code == payload.patient_code,
                                                Patient.discharged_at.is_(None))).scalar_one_or_none()
    if patient is None:
        raise HTTPException(404, "The selected patient is not currently admitted.")
    task = RobotTask(patient_id=patient.id, task_type=payload.task_type, instructions=payload.instructions.strip(),
                     priority=payload.priority, assigned_by=identity)
    db.add(task); db.commit(); db.refresh(task)
    return task_out(task, patient)


@app.get("/api/summaries", response_model=list[SummaryOut])
def summaries(patient_code: str | None = None, _: str = Depends(clinician), db: Session = Depends(get_db)):
    query = select(MedicalSummary, Patient).join(Patient).order_by(MedicalSummary.created_at.desc())
    if patient_code:
        query = query.where(Patient.patient_code == patient_code)
    return [{"id": s.id, "patient_code": p.patient_code, "patient_name": p.full_name, "bed_number": p.bed_number,
             "author": s.author, "clinical_summary": s.summary, "patient_summary": s.patient_summary,
             "temperature_c": s.temperature_c,
             "pulse_bpm": s.pulse_bpm, "ecg_note": s.ecg_note, "created_at": s.created_at}
            for s, p in db.execute(query).all()]


@app.post("/api/robot/tasks/next", response_model=TaskOut)
def claim_next_task(_: None = Depends(robot_authorised), db: Session = Depends(get_db)):
    # Urgent work is prioritised; ties preserve assignment order.
    task = db.execute(select(RobotTask).where(RobotTask.status == "queued").order_by(
        case((RobotTask.priority == "urgent", 0), (RobotTask.priority == "normal", 1), else_=2),
        RobotTask.created_at).with_for_update()).scalars().first()
    if task is None:
        raise HTTPException(404, "No queued tasks.")
    patient = db.get(Patient, task.patient_id)
    task.status, task.started_at = "in_progress", dt.datetime.utcnow()
    db.commit(); db.refresh(task)
    return task_out(task, patient)


@app.post("/api/robot/tasks/{task_id}/complete")
def complete_task(task_id: int, payload: RobotCompleteIn, _: None = Depends(robot_authorised), db: Session = Depends(get_db)):
    task = db.get(RobotTask, task_id)
    if task is None or task.status != "in_progress":
        raise HTTPException(409, "Task is not active.")
    task.status, task.completed_at, task.failure_reason = payload.status, dt.datetime.utcnow(), payload.failure_reason
    if payload.status == "completed":
        clinical_summary = payload.clinical_summary or payload.summary or "Visit completed; no clinical observation supplied."
        patient_summary = payload.patient_summary or "ANNA completed this visit. Please ask your care team if you have questions."
        db.add(MedicalSummary(patient_id=task.patient_id, task_id=task.id, summary=clinical_summary,
                              patient_summary=patient_summary,
                              temperature_c=payload.temperature_c, pulse_bpm=payload.pulse_bpm, ecg_note=payload.ecg_note))
    db.commit()
    return {"ok": True, "return_to_home": True}


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
