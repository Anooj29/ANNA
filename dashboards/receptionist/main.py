"""Receptionist dashboard: registers a new patient, assigns them a unique
patient ID and a bed, captures a reference photo for ANNA's face
recognition, and stores everything in Postgres.

Face *detection* here (just "is there one clear face in this photo?") uses
plain OpenCV, not the `face_recognition`/dlib library the robot uses for
actual face *matching*. That keeps this dashboard installable on a normal
reception-desk PC (Windows included) with no C++ build toolchain required.

Run from the repository root (same convention as the robot's run.sh) so
that ``known_faces/`` resolves to the same directory the robot reads from:

    uvicorn dashboards.receptionist.main:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid

import cv2
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from ..common.config import config
from ..common.database import get_db
from . import crud
from .schemas import BedOut, PatientOut

logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
VALID_BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}

app = FastAPI(title="ANNA - Receptionist Dashboard")

_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def _count_faces(image_path: str) -> int:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not decode image at {image_path}")
    gray = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    faces = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(80, 80))
    return len(faces)


def _safe_folder_name(full_name: str) -> str:
    """Filesystem-safe version of the patient's name, kept unmodified for
    the common case so the robot still greets patients by name (see
    known_faces/README.md) - only collapsing whitespace and stripping
    characters that would break a path.
    """
    cleaned = re.sub(r"[^\w \-']", "", full_name).strip()
    return re.sub(r"\s+", " ", cleaned) or "patient"


def _reference_photo_dir(full_name: str, patient_code: str) -> str:
    """known_faces/<name>/ normally, matching the existing convention. If
    that folder is already taken (e.g. two patients named "John Smith"),
    disambiguate with the patient code rather than overwriting someone
    else's reference photos.
    """
    base = _safe_folder_name(full_name)
    candidate = os.path.join(config.known_faces_dir, base)
    if not os.path.exists(candidate):
        return candidate
    return os.path.join(config.known_faces_dir, f"{base} ({patient_code})")


@app.get("/api/beds", response_model=list[BedOut])
def get_beds(db: Session = Depends(get_db)):
    return crud.list_beds(db)


@app.post("/api/patients", response_model=PatientOut)
async def create_patient(
    full_name: str = Form(...),
    blood_group: str = Form(...),
    height_cm: float = Form(...),
    weight_kg: float = Form(...),
    bed_number: int = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    full_name = full_name.strip()
    blood_group = blood_group.strip().upper()

    if not full_name:
        raise HTTPException(400, "Full name is required.")
    if blood_group not in VALID_BLOOD_GROUPS:
        raise HTTPException(400, f"Blood group must be one of {sorted(VALID_BLOOD_GROUPS)}.")
    if height_cm <= 0 or weight_kg <= 0:
        raise HTTPException(400, "Height and weight must be positive numbers.")

    photo_bytes = await photo.read()
    temp_path = os.path.join(tempfile.gettempdir(), f"anna_reg_{uuid.uuid4().hex}.jpg")
    with open(temp_path, "wb") as handle:
        handle.write(photo_bytes)

    try:
        try:
            face_count = _count_faces(temp_path)
        except Exception:
            raise HTTPException(400, "Could not read that photo. Please retake it.")

        if face_count == 0:
            raise HTTPException(
                400, "No face detected in the photo. Retake it with the patient's face clearly visible."
            )
        if face_count > 1:
            raise HTTPException(
                400, "More than one face detected. Make sure only the patient is in frame."
            )

        try:
            patient = crud.register_patient(
                db,
                full_name=full_name,
                blood_group=blood_group,
                height_cm=height_cm,
                weight_kg=weight_kg,
                bed_number=bed_number,
            )
        except crud.BedUnavailableError as exc:
            raise HTTPException(409, str(exc))

        patient_dir = _reference_photo_dir(full_name, patient.patient_code)
        os.makedirs(patient_dir, exist_ok=True)
        final_path = os.path.join(patient_dir, "reference.jpg")
        os.replace(temp_path, final_path)

        patient = crud.set_patient_photo_path(db, patient, final_path)
        logger.info(
            "Registered patient %s (%s) in bed %d -> %s",
            patient.patient_code, patient.full_name, bed_number, final_path,
        )
        return patient
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# Serve the faces directory so the robot can download new photos.
app.mount("/known_faces", StaticFiles(directory=config.known_faces_dir), name="faces")

# Serve the static frontend last so it doesn't shadow the /api routes above.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
