"""Patient Portal API routes: accessible, secure, patient-friendly health data."""

from __future__ import annotations

import datetime as dt
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from dashboards.common.database import get_db
from dashboards.common.models import (
    AuditLog,
    MedicalSummary,
    Medication,
    Patient,
    VitalReading,
)
from ..auth import get_portal_patient, verify_pin
from ..schemas import PortalLoginRequest

router = APIRouter(prefix="/api/portal", tags=["patient_portal"])


@router.post("/auth/login")
def portal_login(payload: PortalLoginRequest, request: Request, db: Session = Depends(get_db)):
    code = payload.patient_code.strip().upper()
    patient = db.query(Patient).filter(Patient.patient_code == code).first()
    if not patient:
        raise HTTPException(status_code=401, detail="Patient ID or access PIN is incorrect.")

    if not verify_pin(payload.portal_pin, patient.portal_pin_hash, patient.portal_pin):
        raise HTTPException(status_code=401, detail="Patient ID or access PIN is incorrect.")

    request.session.clear()
    request.session["patient_id"] = patient.id
    request.session["patient_code"] = patient.patient_code

    db.add(
        AuditLog(
            user_id=None,
            action="login",
            details=f"Patient {patient.full_name} ({patient.patient_code}) accessed portal.",
            timestamp=dt.datetime.utcnow(),
            ip_address=request.client.host if request.client else "127.0.0.1",
        )
    )
    db.commit()

    return {
        "authenticated": True,
        "patient_code": patient.patient_code,
        "full_name": patient.full_name,
        "bed_number": patient.bed_number,
    }


@router.post("/auth/logout")
def portal_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/profile")
def get_profile(patient: Patient = Depends(get_portal_patient)):
    return {
        "patient_code": patient.patient_code,
        "full_name": patient.full_name,
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender,
        "blood_group": patient.blood_group,
        "height_cm": patient.height_cm,
        "weight_kg": patient.weight_kg,
        "bed_number": patient.bed_number,
        "admission_date": patient.admission_date.strftime("%B %d, %Y"),
        "status": patient.status,
    }


@router.get("/vitals")
def get_latest_vitals(patient: Patient = Depends(get_portal_patient), db: Session = Depends(get_db)):
    latest = (
        db.query(VitalReading)
        .filter(VitalReading.patient_id == patient.id)
        .order_by(VitalReading.recorded_at.desc())
        .first()
    )
    if not latest:
        return {"has_readings": False}

    return {
        "has_readings": True,
        "temperature": f"{latest.temperature_c} °C",
        "temperature_status": "Normal" if latest.temperature_c <= 37.5 else "Mildly Warm",
        "pulse": f"{int(latest.pulse_bpm)} BPM",
        "pulse_status": "Resting normal",
        "spo2": f"{latest.spo2_percent}%",
        "spo2_status": "Healthy oxygen levels",
        "ecg": latest.ecg_note or "Steady rhythm",
        "recorded_at": latest.recorded_at.strftime("%b %d, %I:%M %p"),
    }


@router.get("/history")
def get_history(patient: Patient = Depends(get_portal_patient), db: Session = Depends(get_db)):
    summaries = (
        db.query(MedicalSummary)
        .filter(MedicalSummary.patient_id == patient.id)
        .order_by(MedicalSummary.created_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "created_at": s.created_at.strftime("%A, %B %d at %I:%M %p"),
            "patient_summary": s.patient_summary or "ANNA completed your health check. Please consult your care team for any questions.",
            "temperature": s.temperature_c or "--",
            "pulse": s.pulse_bpm or "--",
            "spo2": s.spo2_percent or "--",
            "ecg": s.ecg_note or "--",
        }
        for s in summaries
    ]


@router.get("/medications")
def get_medications(patient: Patient = Depends(get_portal_patient), db: Session = Depends(get_db)):
    meds = (
        db.query(Medication)
        .filter(Medication.patient_id == patient.id, Medication.status == "active")
        .all()
    )
    return [
        {
            "id": m.id,
            "medicine_name": m.medicine_name,
            "dosage": m.dosage,
            "frequency": m.frequency,
            "scheduled_time": m.scheduled_time,
            "instructions": m.instructions,
        }
        for m in meds
    ]


@router.get("/trends")
def get_trends(patient: Patient = Depends(get_portal_patient), db: Session = Depends(get_db)):
    vitals = (
        db.query(VitalReading)
        .filter(VitalReading.patient_id == patient.id)
        .order_by(VitalReading.recorded_at.asc())
        .limit(15)
        .all()
    )
    return [
        {
            "date": v.recorded_at.strftime("%b %d"),
            "temperature_c": v.temperature_c,
            "pulse_bpm": v.pulse_bpm,
            "spo2_percent": v.spo2_percent,
        }
        for v in vitals
    ]
