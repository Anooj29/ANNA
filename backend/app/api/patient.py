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
from ..services.auth_throttle import check_login_allowed, record_login_failure, clear_login_failures
from ..services.measurements import display
from ..services.thresholds import current_profile

router = APIRouter(prefix="/api/portal", tags=["patient_portal"])


@router.post("/auth/login")
def portal_login(payload: PortalLoginRequest, request: Request, db: Session = Depends(get_db)):
    code = payload.patient_code.strip().upper()
    ip = request.client.host if request.client else "unknown"
    check_login_allowed(db, "portal", code, ip)
    patient = db.query(Patient).filter(Patient.patient_code == code).first()
    if not patient:
        record_login_failure(db, "portal", code, ip)
        raise HTTPException(status_code=401, detail="Patient ID or access PIN is incorrect.")

    if not verify_pin(payload.portal_pin, patient.portal_pin_hash):
        record_login_failure(db, "portal", code, ip)
        raise HTTPException(status_code=401, detail="Patient ID or access PIN is incorrect.")
    clear_login_failures(db, "portal", code, ip)

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
        "date_of_birth": patient.birth_date.isoformat() if patient.birth_date else patient.date_of_birth,
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
        .filter(VitalReading.patient_id == patient.id, VitalReading.quality_status != "simulated")
        .order_by(VitalReading.recorded_at.desc())
        .first()
    )
    if not latest:
        return {"has_readings": False}

    stale = (dt.datetime.utcnow() - latest.recorded_at).total_seconds() > current_profile().stale_hours * 3600

    return {
        "has_readings": True,
        "temperature": display(latest.temperature_c, '°C') if latest.temperature_status == "measured" else "Not available",
        "temperature_status": "Measured" if latest.temperature_status == "measured" else "Measurement needs repeating",
        "pulse": display(latest.pulse_bpm, 'BPM') if latest.pulse_status == "measured" else "Not available",
        "pulse_status": "Measured" if latest.pulse_status == "measured" else "Measurement needs repeating",
        "spo2": display(latest.spo2_percent, '%') if latest.spo2_status == "measured" else "Not available",
        "spo2_status": "Measured" if latest.spo2_status == "measured" else "Measurement needs repeating",
        "ecg": latest.ecg_note or "Not available",
        "recorded_at": latest.recorded_at.strftime("%b %d, %I:%M %p"),
        "source": latest.source,
        "freshness_status": "New measurement recommended" if stale else "Recently measured",
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
            "schedule_times": m.schedule_times,
            "instructions": m.instructions,
        }
        for m in meds
    ]


@router.get("/trends")
def get_trends(patient: Patient = Depends(get_portal_patient), db: Session = Depends(get_db)):
    vitals = list(reversed((
        db.query(VitalReading)
        .filter(VitalReading.patient_id == patient.id, VitalReading.quality_status != "simulated")
        .order_by(VitalReading.recorded_at.desc())
        .limit(30)
        .all()
    )))
    return [
        {
            "date": v.recorded_at.strftime("%b %d"),
            "temperature_c": v.temperature_c if v.temperature_status == "measured" else None,
            "pulse_bpm": v.pulse_bpm if v.pulse_status == "measured" else None,
            "spo2_percent": v.spo2_percent if v.spo2_status == "measured" else None,
        }
        for v in vitals
    ]
