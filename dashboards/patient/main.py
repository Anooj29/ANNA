"""Patient dashboard: allows patients to view their own health reports."""

from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Cookie
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from ..common.database import get_db
from . import crud
from .schemas import PatientInfoOut, PatientSessionOut

logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="ANNA - Patient Portal")

@app.post("/api/login")
def login(patient_code: str, response_cookie = Cookie(), db: Session = Depends(get_db)):
    patient = crud.get_patient_by_code(db, patient_code)
    if not patient:
        raise HTTPException(401, "Invalid patient code.")

    # Simple session: set a cookie with the patient code
    # In a real app, we would use a secure JWT
    response_cookie.set("patient_code", patient_code)
    return {"full_name": patient.full_name}

@app.get("/api/my-info")
def get_my_info(patient_code: str = Cookie(None), db: Session = Depends(get_db)):
    if not patient_code:
        raise HTTPException(401, "Not logged in.")

    patient = crud.get_patient_by_code(db, patient_code)
    if not patient:
        raise HTTPException(404, "Patient not found.")

    return patient

@app.get("/api/my-sessions", response_model=list[PatientSessionOut])
def get_my_sessions(patient_code: str = Cookie(None), db: Session = Depends(get_db)):
    if not patient_code:
        raise HTTPException(401, "Not logged in.")

    patient = crud.get_patient_by_code(db, patient_code)
    if not patient:
        raise HTTPException(404, "Patient not found.")

    return crud.get_sessions_for_patient(db, patient.full_name)

# Serve static frontend
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
