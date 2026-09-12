"""ORM models shared by all three dashboards.

Only Patient and Bed exist so far (what the receptionist dashboard needs).
The clinician dashboard will likely add a Task/Assignment table that
references Patient; the patient dashboard will likely add a Report table.
Both can import Patient/Bed from here without duplicating anything.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String

from .database import Base


class Bed(Base):
    __tablename__ = "beds"

    bed_number = Column(Integer, primary_key=True)
    is_occupied = Column(Boolean, default=False, nullable=False)


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_code = Column(String(20), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    blood_group = Column(String(5), nullable=False)
    height_cm = Column(Float, nullable=False)
    weight_kg = Column(Float, nullable=False)

    # Path to the reference photo ANNA's face-recognition step reads,
    # e.g. "known_faces/Alice Rao/reference.jpg".
    photo_path = Column(String(255), nullable=False)

    # Deliberately NOT unique: beds get reused across many patients over
    # time, so this is "which bed were/are they in", not a 1:1 link. Whether
    # they're the CURRENT occupant is: bed_number is set AND discharged_at
    # is still null. Bed.is_occupied is the fast source of truth for the
    # ward map; this is how you find who's actually in a given bed.
    bed_number = Column(Integer, ForeignKey("beds.bed_number"), nullable=True)

    registered_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    discharged_at = Column(DateTime, nullable=True)
