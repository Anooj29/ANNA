"""ORM models shared by all three dashboards.

Only Patient and Bed exist so far (what the receptionist dashboard needs).
The clinician dashboard will likely add a Task/Assignment table that
references Patient; the patient dashboard will likely add a Report table.
Both can import Patient/Bed from here without duplicating anything.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship

from .database import Base


class Bed(Base):
    __tablename__ = "beds"

    bed_number = Column(Integer, primary_key=True)
    is_occupied = Column(Boolean, default=False, nullable=False)

    patient = relationship("Patient", back_populates="bed", uselist=False)


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

    bed_number = Column(Integer, ForeignKey("beds.bed_number"), unique=True, nullable=True)
    bed = relationship("Bed", back_populates="patient")

    registered_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    sessions = relationship("PatientSession", back_populates="patient")
    assignments = relationship("Assignment", back_populates="patient")


class PatientSession(Base):
    __tablename__ = "patient_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_name = Column(String(120), nullable=False, index=True)
    emotion = Column(String(50))
    temperature = Column(String(50))
    pulse = Column(String(50))
    ecg = Column(String(50))
    health_report = Column(Text)
    answers = Column(JSON)
    timestamp = Column(DateTime, default=dt.datetime.utcnow)

    # Link to Patient via name (matching the sync_sessions.py logic)
    # In a real system, we'd use patient_id, but we keep this for now.
    patient = relationship("Patient", primaryjoin="and_(PatientSession.patient_name==Patient.full_name)", foreign_keys=["patient_name"], overlaps="patient")


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    assigned_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)

    patient = relationship("Patient", back_populates="assignments")
