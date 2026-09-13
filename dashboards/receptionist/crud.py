from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common.config import config
from ..common.models import Bed, Patient


class BedUnavailableError(Exception):
    """Raised when the requested bed is already occupied or doesn't exist."""


def list_beds(db: Session) -> list[Bed]:
    return db.execute(select(Bed).order_by(Bed.bed_number)).scalars().all()


def register_patient(
    db: Session,
    *,
    full_name: str,
    blood_group: str,
    height_cm: float,
    weight_kg: float,
    bed_number: int,
) -> Patient:
    """Create a patient, assign them the given bed, and hand back a patient
    with its final patient_code filled in. Raises BedUnavailableError if the
    bed was taken between the dashboard loading the ward map and the
    receptionist hitting submit (SELECT ... FOR UPDATE prevents two
    concurrent requests from double-booking the same bed).
    """
    bed = db.execute(
        select(Bed).where(Bed.bed_number == bed_number).with_for_update()
    ).scalar_one_or_none()
    if bed is None or bed.is_occupied:
        raise BedUnavailableError(f"Bed {bed_number} is not available.")

    # patient_code depends on the autoincrement id, so insert first with a
    # placeholder, flush to get the id, then fill in the real code.
    patient = Patient(
        full_name=full_name,
        blood_group=blood_group,
        height_cm=height_cm,
        weight_kg=weight_kg,
        photo_path="",
        patient_code="PENDING",
    )
    db.add(patient)
    db.flush()

    patient.patient_code = f"{config.patient_id_prefix}-{patient.id:05d}"
    bed.is_occupied = True
    patient.bed_number = bed_number

    db.commit()
    db.refresh(patient)
    return patient


def set_patient_photo_path(db: Session, patient: Patient, photo_path: str) -> Patient:
    patient.photo_path = photo_path
    db.commit()
    db.refresh(patient)
    return patient
