"""Patient-facing portal. A patient ID plus confidential access PIN is required."""
from __future__ import annotations

import hmac
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from ..common.config import config
from ..common.database import get_db
from ..common.models import MedicalSummary, Patient

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app = FastAPI(title="ANNA - Patient Portal")
app.add_middleware(SessionMiddleware, secret_key=config.session_secret, same_site="lax", https_only=False)


class PortalLogin(BaseModel):
    patient_code: str = Field(min_length=3, max_length=20)
    portal_pin: str = Field(min_length=6, max_length=12)


def portal_patient(request: Request, db: Session = Depends(get_db)) -> Patient:
    patient_id = request.session.get("patient_id")
    patient = db.get(Patient, patient_id) if patient_id else None
    if patient is None:
        raise HTTPException(401, "Please sign in with your patient ID and access PIN.")
    return patient


@app.post("/api/auth/login")
def login(payload: PortalLogin, request: Request, db: Session = Depends(get_db)):
    patient = db.execute(select(Patient).where(Patient.patient_code == payload.patient_code.strip().upper())).scalar_one_or_none()
    if patient is None or not patient.portal_pin or not hmac.compare_digest(patient.portal_pin, payload.portal_pin.strip()):
        raise HTTPException(401, "Patient ID or access PIN is incorrect. Ask your care team for help.")
    request.session.clear()
    request.session["patient_id"] = patient.id
    return {"patient_code": patient.patient_code, "full_name": patient.full_name}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/profile")
def profile(patient: Patient = Depends(portal_patient)):
    return {"patient_code": patient.patient_code, "full_name": patient.full_name, "blood_group": patient.blood_group,
            "registered_at": patient.registered_at, "discharged_at": patient.discharged_at}


@app.get("/api/history")
def history(patient: Patient = Depends(portal_patient), db: Session = Depends(get_db)):
    entries = db.execute(select(MedicalSummary).where(MedicalSummary.patient_id == patient.id)
                         .order_by(MedicalSummary.created_at.desc())).scalars().all()
    return [{"created_at": item.created_at, "patient_summary": item.patient_summary or
             "This older ANNA record has no patient-friendly explanation. Please ask your care team to review it with you.",
             "temperature_c": item.temperature_c, "pulse_bpm": item.pulse_bpm, "ecg_note": item.ecg_note}
            for item in entries]


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
