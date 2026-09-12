from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common.config import config
from ..common.models import Bed, Patient


class BedUnavailableError(Exception):
    """Raised when the requested bed is already occupied, doesn't exist,
    or (for discharge) isn't currently occupied.
    """


def get_current_occupant(db: Session, bed_number: int) -> Patient | None:
    return db.execute(
        select(Patient).where(Patient.bed_number == bed_number, Patient.discharged_at.is_(None))
    ).scalar_one_or_none()


def list_beds(db: Session) -> list[dict]:
    """Every bed, with the current occupant's name/code/admission time
    filled in when occupied - everything the ward map needs in one call.
    """
    beds = db.execute(select(Bed).order_by(Bed.bed_number)).scalars().all()
    current_patients = db.execute(
        select(Patient).where(Patient.discharged_at.is_(None))
    ).scalars().all()
    by_bed = {p.bed_number: p for p in current_patients if p.bed_number is not None}

    result = []
    for bed in beds:
        occupant = by_bed.get(bed.bed_number)
        result.append({
            "bed_number": bed.bed_number,
            "is_occupied": bed.is_occupied,
            "occupant_code": occupant.patient_code if occupant else None,
            "occupant_name": occupant.full_name if occupant else None,
            "admitted_at": occupant.registered_at if occupant else None,
        })
    return result


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


def discharge_patient(db: Session, bed_number: int) -> Patient:
    """Free up a bed when its patient leaves. The patient row is kept (not
    deleted) with discharged_at set, so registration history survives -
    only Bed.is_occupied flips back to False, making the bed assignable
    to a new patient again.
    """
    bed = db.execute(
        select(Bed).where(Bed.bed_number == bed_number).with_for_update()
    ).scalar_one_or_none()
    if bed is None or not bed.is_occupied:
        raise BedUnavailableError(f"Bed {bed_number} is not currently occupied.")

    patient = get_current_occupant(db, bed_number)
    if patient is None:
        # Data got out of sync somehow - don't leave the bed stuck occupied
        # with no one actually in it.
        bed.is_occupied = False
        db.commit()
        raise BedUnavailableError(
            f"Bed {bed_number} was marked occupied but had no active patient on record; it has been freed."
        )

    patient.discharged_at = dt.datetime.utcnow()
    bed.is_occupied = False

    db.commit()
    db.refresh(patient)
    return patient


def set_patient_photo_path(db: Session, patient: Patient, photo_path: str) -> Patient:
    patient.photo_path = photo_path
    db.commit()
    db.refresh(patient)
    return patient
