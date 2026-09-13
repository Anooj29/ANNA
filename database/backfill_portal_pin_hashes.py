"""One-time, non-destructive legacy PIN backfill; run after backing up the database.

Existing plaintext PINs are hashed only when a hash is missing, then cleared.
Run with the normal DB_ENGINE/POSTGRES_* environment before deployment.
"""

from dashboards.common.database import SessionLocal
from dashboards.common.models import Patient
from backend.app.auth import hash_password


def backfill() -> int:
    with SessionLocal.begin() as db:
        patients = db.query(Patient).filter(Patient.portal_pin.is_not(None)).all()
        for patient in patients:
            if not patient.portal_pin_hash:
                patient.portal_pin_hash = hash_password(patient.portal_pin)
            patient.portal_pin = None
        return len(patients)


if __name__ == "__main__":
    print(f"Cleared legacy plaintext PINs for {backfill()} patients.")
