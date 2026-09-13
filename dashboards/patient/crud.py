from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common.models import Patient, PatientSession


def get_patient_by_code(db: Session, code: str) -> Patient | None:
    return db.execute(select(Patient).where(Patient.patient_code == code)).scalar_one_or_none()


def get_sessions_for_patient(db: Session, full_name: str) -> list[PatientSession]:
    return db.execute(
        select(PatientSession).where(PatientSession.patient_name == full_name).order_by(PatientSession.timestamp.desc())
    ).scalars().all()
