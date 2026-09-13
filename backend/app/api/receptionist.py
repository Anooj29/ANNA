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
import cv2
import numpy as np

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dashboards.common.config import config
from dashboards.common.database import get_db
from dashboards.common.models import Bed, Patient, AuditLog, User
from dashboards.receptionist.face_check import count_faces
from ..auth import hash_password, require_role
from ..schemas import BedResponse, PatientResponseModel, TaskCreateRequest
from pydantic import BaseModel
from ..websocket import ws_manager

logger = logging.getLogger("anna.receptionist")
router = APIRouter(prefix="/api", tags=["receptionist"], dependencies=[Depends(require_role("receptionist", "admin"))])


class AssignmentRequest(BaseModel):
    bed_number: int | None = None
    doctor_id: int | None = None


@router.get("/receptionist/doctors")
def available_doctors(db: Session = Depends(get_db)):
    return [{"id": u.id, "name": u.full_name} for u in db.query(User).filter(User.role == "doctor", User.is_active.is_(True)).order_by(User.full_name).all()]


@router.get("/receptionist/patients")
def operational_patients(query: str = "", ward: str = "all", status: str = "all",
                         page: int | None = Query(default=None, ge=1),
                         page_size: int = Query(default=20, ge=1, le=100),
                         db: Session = Depends(get_db)):
    """Patient directory restricted to information needed for reception operations."""
    records = db.query(Patient).order_by(Patient.admission_date.desc())
    if query.strip():
        term = f"%{query.strip()}%"
        criteria = Patient.patient_code.ilike(term) | Patient.full_name.ilike(term) | Patient.phone.ilike(term)
        if query.strip().isdigit():
            criteria = criteria | (Patient.bed_number == int(query.strip()))
        records = records.filter(criteria)
    if ward != "all":
        if ward not in {"Ward A", "Ward B"}:
            raise HTTPException(status_code=422, detail="Unknown ward.")
        records = records.join(Bed, Bed.bed_number == Patient.bed_number).filter(Bed.ward == ward)
    if status != "all":
        if status not in {"admitted", "discharged"}:
            raise HTTPException(status_code=422, detail="Unknown patient status.")
        records = records.filter(Patient.status == status)
    total = records.count() if page is not None else None
    selected = records.offset((page - 1) * page_size).limit(page_size).all() if page is not None else records.limit(100).all()
    items = [
        {"patient_code": p.patient_code, "full_name": p.full_name,
         "gender": p.gender, "blood_group": p.blood_group,
         "bed_number": p.bed_number, "admission_date": p.admission_date,
         "status": p.status, "assigned_doctor_id": p.assigned_doctor_id}
        for p in selected
    ]
    if page is not None:
        return {"items": items, "total": total, "page": page, "page_size": page_size,
                "pages": (total + page_size - 1) // page_size}
    return items


@router.patch("/receptionist/patients/{patient_code}/assignment")
async def update_assignment(patient_code: str, payload: AssignmentRequest, request: Request, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_code == patient_code.strip().upper(), Patient.status == "admitted").first()
    if not patient:
        raise HTTPException(status_code=404, detail="Admitted patient not found.")
    if payload.doctor_id is not None:
        doctor = db.query(User).filter(User.id == payload.doctor_id, User.role == "doctor", User.is_active.is_(True)).first()
        if not doctor:
            raise HTTPException(status_code=422, detail="Selected doctor is unavailable.")
        patient.assigned_doctor_id = doctor.id
    if payload.bed_number is not None and payload.bed_number != patient.bed_number:
        new_bed = db.query(Bed).filter(Bed.bed_number == payload.bed_number).with_for_update().first()
        if not new_bed or new_bed.is_occupied or new_bed.status != "available":
            raise HTTPException(status_code=409, detail="Selected bed is unavailable.")
        old_bed = db.query(Bed).filter(Bed.bed_number == patient.bed_number).with_for_update().first()
        if old_bed:
            old_bed.is_occupied = False
            old_bed.patient_id = None
            old_bed.status = "available"
        new_bed.is_occupied = True
        new_bed.patient_id = patient.id
        new_bed.status = "occupied"
        patient.bed_number = new_bed.bed_number
    db.add(AuditLog(user_id=request.session.get("user_id"), actor_role="receptionist", action="patient_assignment",
                    entity_type="patient", entity_id=patient.patient_code, source="web",
                    details=f"Assignment updated for {patient.patient_code}.", timestamp=dt.datetime.utcnow(),
                    ip_address=request.client.host if request.client else None))
    db.commit()
    await ws_manager.broadcast("patient_updated", {"patient_code": patient.patient_code, "bed_number": patient.bed_number})
    await ws_manager.broadcast("bed_updated", {"bed_number": patient.bed_number})
    return {"ok": True, "patient_code": patient.patient_code, "bed_number": patient.bed_number,
            "assigned_doctor_id": patient.assigned_doctor_id}


@router.post("/receptionist/tasks")
async def assign_routine_task(payload: TaskCreateRequest, request: Request, db: Session = Depends(get_db)):
    """Preserve the existing reception workflow without exposing clinical task APIs."""
    if payload.task_type != "ANNA Health Check" or payload.priority != "normal":
        raise HTTPException(status_code=403, detail="Reception may assign routine ANNA health checks only.")
    from .clinician import create_task
    return await create_task(payload, request, db)


def safe_folder_name(full_name: str) -> str:
    cleaned = re.sub(r"[^\w \-']", "", full_name).strip()
    return re.sub(r"\s+", " ", cleaned) or "patient"


def reference_photo_dir(full_name: str, patient_code: str) -> str:
    base = safe_folder_name(full_name)
    candidate = os.path.join(config.known_faces_dir, base)
    if not os.path.exists(candidate):
        return candidate
    return os.path.join(config.known_faces_dir, f"{base} ({patient_code})")


async def validated_photo_temp(photo: UploadFile) -> str:
    if photo.content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(status_code=415, detail="Upload a JPEG or PNG patient photo.")
    content = await photo.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Patient photo exceeds the 5 MB limit.")
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or not (160 <= image.shape[0] <= 4000 and 160 <= image.shape[1] <= 4000):
        raise HTTPException(status_code=422, detail="Patient photo is unreadable or outside supported dimensions.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp:
        temp_path = temp.name
    if not cv2.imwrite(temp_path, image):
        os.remove(temp_path)
        raise HTTPException(status_code=422, detail="Patient photo could not be processed.")
    return temp_path


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
    temp_path = await validated_photo_temp(photo)

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
    assigned_doctor_id: Optional[int] = Form(None),
    photo: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    parsed_birth_date = None
    if date_of_birth:
        try:
            parsed_birth_date = dt.date.fromisoformat(date_of_birth)
        except ValueError:
            raise HTTPException(status_code=422, detail="Date of birth must use YYYY-MM-DD.")
        if parsed_birth_date > dt.date.today():
            raise HTTPException(status_code=422, detail="Date of birth cannot be in the future.")
    # Verify bed availability
    bed = db.query(Bed).filter(Bed.bed_number == bed_number).with_for_update().first()
    if not bed:
        raise HTTPException(status_code=404, detail=f"Bed {bed_number} does not exist.")
    if bed.is_occupied or bed.status != "available":
        raise HTTPException(status_code=409, detail=f"Bed {bed_number} is already occupied.")
    if assigned_doctor_id is not None:
        doctor = db.query(User).filter(User.id == assigned_doctor_id, User.role == "doctor", User.is_active.is_(True)).first()
        if not doctor:
            raise HTTPException(status_code=422, detail="Selected doctor is unavailable.")

    # Validate Photo
    suffix = ".jpg"
    temp_path = await validated_photo_temp(photo)

    try:
        face_count = count_faces(temp_path)
        if face_count != 1:
            raise HTTPException(
                status_code=400,
                detail="Photo must contain exactly one clearly visible face.",
            )
    except Exception as e:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        if isinstance(e, HTTPException):
            raise e
        logger.exception("Patient photo validation failed")
        raise HTTPException(status_code=400, detail="Patient photo could not be validated.")

    # Generate 6-digit Portal PIN
    portal_pin = f"{secrets.randbelow(1_000_000):06d}"
    pin_hash = hash_password(portal_pin)

    # Insert patient
    patient = Patient(
        patient_code="PENDING",
        full_name=full_name.strip(),
        date_of_birth=date_of_birth,
        birth_date=parsed_birth_date,
        gender=gender,
        blood_group=blood_group.strip().upper(),
        height_cm=height_cm,
        weight_kg=weight_kg,
        phone=phone.strip() if phone else None,
        emergency_contact=emergency_contact.strip() if emergency_contact else None,
        address=address.strip() if address else None,
        photo_path="",
        bed_number=bed_number,
        assigned_doctor_id=assigned_doctor_id,
        admission_date=dt.datetime.utcnow(),
        portal_pin=None,
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
    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            os.remove(target_photo)
            os.rmdir(target_dir)
        except OSError:
            pass
        raise
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
        date_of_birth=patient.birth_date.isoformat() if patient.birth_date else patient.date_of_birth,
        gender=patient.gender,
        blood_group=patient.blood_group,
        height_cm=patient.height_cm,
        weight_kg=patient.weight_kg,
        phone=patient.phone,
        emergency_contact=patient.emergency_contact,
        address=patient.address,
        photo_path=None,
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
