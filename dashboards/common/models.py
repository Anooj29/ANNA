"""ORM models shared by all three dashboards.

Patient and Bed support reception; RobotTask and MedicalSummary support the
clinician workflow. A future patient dashboard can import these shared
records without duplicating anything.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

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
    # A patient ID is an identifier, not a password. This short access code
    # authorises the patient portal alongside the patient ID.
    portal_pin = Column(String(12), nullable=True)


class RobotTask(Base):
    """A clinician-requested visit. The robot claims queued work in order."""
    __tablename__ = "robot_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)
    instructions = Column(Text, nullable=False, default="")
    priority = Column(String(12), nullable=False, default="normal")
    status = Column(String(20), nullable=False, default="queued", index=True)
    assigned_by = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)


class MedicalSummary(Base):
    """Visit record visible only after a clinician session is authenticated."""
    __tablename__ = "medical_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("robot_tasks.id"), nullable=True, index=True)
    author = Column(String(120), nullable=False, default="ANNA robot")
    summary = Column(Text, nullable=False)
    # ``summary`` is the clinician-facing observation for backwards
    # compatibility. ``patient_summary`` is a separate plain-language view.
    patient_summary = Column(Text, nullable=True)
    temperature_c = Column(String(30), nullable=True)
    pulse_bpm = Column(String(30), nullable=True)
    ecg_note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
