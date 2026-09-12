"""Receptionist & Bed Management API routes."""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import secrets
import shutil
import tempfile
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dashboards.common.config import config
from dashboards.common.database import get_db
from dashboards.common.models import Bed, Patient, AuditLog
from dashboards.receptionist.face_check import count_faces
from ..auth import hash_password
from ..schemas import BedResponse, PatientResponseModel
from ..websocket import ws_manager

logger = logging.getLogger("anna.receptionist")
router = APIRouter(prefix="/api", tags=["receptionist"])


def safe_folder_name(full_name: str) -> str:
    cleaned = re.sub(r"[^\w \-']", "", full_name).strip()
    return re.sub(r"\s+", " ", cleaned) or "patient"


def reference_photo_dir(full_name: str, patient_code: str) -> str:
    base = safe_folder_name(full_name)
    candidate = os.path.join(config.known_faces_dir, base)
    if not os.path.exists(candidate):
        return candidate
    return os.path.join(config.known_faces_dir, f"{base} ({patient_code})")


@router.get("/receptionist/stats")
def receptionist_stats(db: Session = Depends(get_db)):
    total_beds = db.query(Bed).count()
    occupied_beds = db.query(Bed).filter(Bed.is_occupied.is_(True)).count()
    available_beds = total_beds - occupied_beds

    today_start = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    admissions_today = (
        db.query(Patient)
        .filter(Patient.admission_date >= today_start)
        .count()
    )
    discharges_today = (
        db.query(Patient)
        .filter(Patient.discharge_date >= today_start)
        .count()
    )
    active_patients = db.query(Patient).filter(Patient.status == "admitted").count()

    return {
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "available_beds": available_beds,
        "admissions_today": admissions_today,
        "discharges_today": discharges_today,
        "active_patients": active_patients,
    }


@router.get("/receptionist/analytics")
def receptionist_analytics(db: Session = Depends(get_db)):
    """Return historical and ward breakdown analytics for receptionist charts."""
    # 1. Ward Occupancy breakdown
    ward_a_total = db.query(Bed).filter(Bed.ward == "Ward A").count()
    ward_a_occupied = db.query(Bed).filter(Bed.ward == "Ward A", Bed.is_occupied.is_(True)).count()
    ward_b_total = db.query(Bed).filter(Bed.ward == "Ward B").count()
    ward_b_occupied = db.query(Bed).filter(Bed.ward == "Ward B", Bed.is_occupied.is_(True)).count()

    # 2. Last 7 days admission vs discharge counts
    days_labels = []
    admissions_7d = []
    discharges_7d = []
    now = dt.datetime.utcnow()

    for i in range(6, -1, -1):
        day_start = (now - dt.timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + dt.timedelta(days=1)
        days_labels.append(day_start.strftime("%a %d"))

        adm_cnt = db.query(Patient).filter(
            Patient.admission_date >= day_start,
            Patient.admission_date < day_end
        ).count()
        dis_cnt = db.query(Patient).filter(
            Patient.discharge_date >= day_start,
            Patient.discharge_date < day_end
        ).count()

        admissions_7d.append(adm_cnt)
        discharges_7d.append(dis_cnt)

    return {
        "ward_occupancy": {
            "ward_a": {"total": ward_a_total, "occupied": ward_a_occupied, "available": ward_a_total - ward_a_occupied},
            "ward_b": {"total": ward_b_total, "occupied": ward_b_occupied, "available": ward_b_total - ward_b_occupied},
        },
        "admissions_vs_discharges": {
            "labels": days_labels,
            "admissions": admissions_7d,
            "discharges": discharges_7d,
        }
    }


@router.get("/beds", response_model=List[BedResponse])
def get_beds(db: Session = Depends(get_db)):
    beds = db.query(Bed).order_by(Bed.bed_number).all()
    active_patients = db.query(Patient).filter(Patient.status == "admitted").all()
    by_bed = {p.bed_number: p for p in active_patients if p.bed_number is not None}

    results = []
    for bed in beds:
        occupant = by_bed.get(bed.bed_number)
        results.append(
            BedResponse(
                id=bed.id,
                bed_number=bed.bed_number,
                ward=bed.ward,
                bed_type=bed.bed_type,
                is_occupied=bed.is_occupied,
                status=bed.status,
                occupant_code=occupant.patient_code if occupant else None,
                occupant_name=occupant.full_name if occupant else None,
                admitted_at=occupant.admission_date if occupant else None,
            )
        )
    return results


@router.post("/photo-check")
async def check_uploaded_photo(photo: UploadFile = File(...)):
    suffix = os.path.splitext(photo.filename or "")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        shutil.copyfileobj(photo.file, temp)
        temp_path = temp.name

    try:
        faces = count_faces(temp_path)
        if faces == 0:
            return {"passed": False, "face_count": 0, "message": "No face detected. Please face the camera with good lighting."}
        if faces > 1:
            return {"passed": False, "face_count": faces, "message": "Multiple faces detected. Ensure only the patient is in frame."}
        return {"passed": True, "face_count": 1, "message": "Face verified successfully."}
    except Exception as exc:
        logger.exception("Photo check error: %s", exc)
        return {"passed": False, "face_count": 0, "message": "Could not process image file."}
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


@router.post("/patients", response_model=PatientResponseModel)
async def register_patient(
    full_name: str = Form(...),
    date_of_birth: Optional[str] = Form(None),
    gender: str = Form("Unspecified"),
    blood_group: str = Form(...),
    height_cm: float = Form(...),
    weight_kg: float = Form(...),
    phone: Optional[str] = Form(None),
    emergency_contact: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    bed_number: int = Form(...),
    photo: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    # Verify bed availability
    bed = db.query(Bed).filter(Bed.bed_number == bed_number).with_for_update().first()
    if not bed:
        raise HTTPException(status_code=404, detail=f"Bed {bed_number} does not exist.")
    if bed.is_occupied:
        raise HTTPException(status_code=409, detail=f"Bed {bed_number} is already occupied.")

    # Validate Photo
    suffix = os.path.splitext(photo.filename or "")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        shutil.copyfileobj(photo.file, temp)
        temp_path = temp.name

    try:
        face_count = count_faces(temp_path)
        if face_count != 1:
            raise HTTPException(
                status_code=400,
                detail="Photo must contain exactly one clearly visible face.",
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=f"Photo validation failed: {str(e)}")

    # Generate 6-digit Portal PIN
    portal_pin = f"{secrets.randbelow(1_000_000):06d}"
    pin_hash = hash_password(portal_pin)

    # Insert patient
    patient = Patient(
        patient_code="PENDING",
        full_name=full_name.strip(),
        date_of_birth=date_of_birth,
        gender=gender,
        blood_group=blood_group.strip().upper(),
        height_cm=height_cm,
        weight_kg=weight_kg,
        phone=phone.strip() if phone else None,
        emergency_contact=emergency_contact.strip() if emergency_contact else None,
        address=address.strip() if address else None,
        photo_path="",
        bed_number=bed_number,
        admission_date=dt.datetime.utcnow(),
        portal_pin=portal_pin,
        portal_pin_hash=pin_hash,
        status="admitted",
    )
    db.add(patient)
    db.flush()

    # Formulate patient code and store reference photo
    patient_code = f"{config.patient_id_prefix}-{patient.id:05d}"
    patient.patient_code = patient_code

    target_dir = reference_photo_dir(full_name, patient_code)
    os.makedirs(target_dir, exist_ok=True)
    target_photo = os.path.join(target_dir, f"reference{suffix}")
    shutil.move(temp_path, target_photo)
    patient.photo_path = target_photo

    # Lock bed
    bed.is_occupied = True
    bed.patient_id = patient.id
    bed.status = "occupied"

    # Audit log
    db.add(
        AuditLog(
            user_id=request.session.get("user_id") if request else None,
            action="patient_creation",
            details=f"Admitted patient {patient.full_name} ({patient.patient_code}) to Bed {bed_number}.",
            timestamp=dt.datetime.utcnow(),
            ip_address=request.client.host if request and request.client else "127.0.0.1",
        )
    )
    db.commit()
    db.refresh(patient)

    # Broadcast real-time WebSocket event
    await ws_manager.broadcast(
        "patient_admitted",
        {
            "patient_code": patient.patient_code,
            "full_name": patient.full_name,
            "bed_number": patient.bed_number,
            "admission_date": patient.admission_date.isoformat(),
        },
    )

    return PatientResponseModel(
        id=patient.id,
        patient_code=patient.patient_code,
        full_name=patient.full_name,
        date_of_birth=patient.date_of_birth,
        gender=patient.gender,
        blood_group=patient.blood_group,
        height_cm=patient.height_cm,
        weight_kg=patient.weight_kg,
        phone=patient.phone,
        emergency_contact=patient.emergency_contact,
        address=patient.address,
        photo_path=patient.photo_path,
        bed_number=patient.bed_number,
        admission_date=patient.admission_date,
        discharge_date=patient.discharge_date,
        status=patient.status,
        portal_pin=portal_pin,
        risk_level="NORMAL",
    )


@router.post("/beds/{bed_number}/discharge")
async def discharge_patient(
    bed_number: int,
    request: Request = None,
    db: Session = Depends(get_db),
):
    bed = db.query(Bed).filter(Bed.bed_number == bed_number).with_for_update().first()
    if not bed or not bed.is_occupied:
        raise HTTPException(status_code=409, detail=f"Bed {bed_number} is not currently occupied.")

    patient = (
        db.query(Patient)
        .filter(Patient.bed_number == bed_number, Patient.status == "admitted")
        .first()
    )
    if not patient:
        bed.is_occupied = False
        bed.patient_id = None
        bed.status = "available"
        db.commit()
        raise HTTPException(status_code=404, detail="No active patient found in that bed. Bed has been reset.")

    patient.discharge_date = dt.datetime.utcnow()
    patient.status = "discharged"
    patient.bed_number = None

    bed.is_occupied = False
    bed.patient_id = None
    bed.status = "available"

    db.add(
        AuditLog(
            user_id=request.session.get("user_id") if request else None,
            action="discharge",
            details=f"Discharged patient {patient.full_name} ({patient.patient_code}) from Bed {bed_number}.",
            timestamp=dt.datetime.utcnow(),
            ip_address=request.client.host if request and request.client else "127.0.0.1",
        )
    )
    db.commit()

    # Broadcast real-time WebSocket event
    await ws_manager.broadcast(
        "patient_discharged",
        {
            "patient_code": patient.patient_code,
            "full_name": patient.full_name,
            "bed_number": bed_number,
        },
    )

    return {"ok": True, "patient_code": patient.patient_code, "discharged_at": patient.discharge_date}
