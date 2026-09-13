from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common.models import Patient, PatientSession, Assignment


def list_patients(db: Session) -> list[Patient]:
    return db.execute(select(Patient).order_by(Patient.full_name)).scalars().all()


def get_patient_sessions(db: Session, patient_name: str) -> list[PatientSession]:
    return db.execute(
        select(PatientSession).where(PatientSession.patient_name == patient_name).order_by(PatientSession.timestamp.desc())
    ).scalars().all()


def create_assignment(db: Session, patient_id: int) -> Assignment:
    assignment = Assignment(patient_id=patient_id, is_completed=False)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment
