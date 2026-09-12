"""Normalized relational ORM models for ANNA Hospital System.

PostgreSQL 18.6 primary database schema shared by:
- Receptionist Dashboard
- Clinician Dashboard
- Patient Portal
- ANNA Robot Controller
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import relationship, synonym

from .database import Base


class User(Base):
    """System users: receptionist, doctor, patient."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, index=True)  # receptionist, doctor, patient
    full_name = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class Bed(Base):
    """Hospital ward beds."""
    __tablename__ = "beds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bed_number = Column(Integer, unique=True, nullable=False, index=True)
    ward = Column(String(50), default="Ward A", nullable=False)
    bed_type = Column(String(50), default="General", nullable=False)  # General, ICU, Step-Down
    is_occupied = Column(Boolean, default=False, nullable=False, index=True)
    patient_id = Column(Integer, nullable=True)
    status = Column(String(20), default="available", nullable=False)  # available, occupied, maintenance


class Patient(Base):
    """Admitted and historical hospital patients."""
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_code = Column(String(20), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False, index=True)
    date_of_birth = Column(String(20), nullable=True)
    gender = Column(String(20), default="Unspecified", nullable=False)
    blood_group = Column(String(5), nullable=False)
    height_cm = Column(Float, nullable=False)
    weight_kg = Column(Float, nullable=False)
    phone = Column(String(30), nullable=True)
    emergency_contact = Column(String(30), nullable=True)
    address = Column(Text, nullable=True)

    # Reference photo enrolled for ANNA face recognition
    photo_path = Column(String(255), nullable=False)
    face_encoding = Column(Text, nullable=True)

    bed_number = Column(Integer, ForeignKey("beds.bed_number"), nullable=True, index=True)

    admission_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
    discharge_date = Column(DateTime, nullable=True, index=True)

    # Backwards compatibility synonyms for existing code:
    registered_at = synonym("admission_date")
    discharged_at = synonym("discharge_date")

    portal_pin = Column(String(12), nullable=True)
    portal_pin_hash = Column(String(255), nullable=True)
    status = Column(String(20), default="admitted", nullable=False, index=True)  # admitted, discharged

    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)

    # Relationships
    tasks = relationship("RobotTask", back_populates="patient", cascade="all, delete-orphan")
    sessions = relationship("HealthCheckSession", back_populates="patient", cascade="all, delete-orphan")
    vitals = relationship("VitalReading", back_populates="patient", cascade="all, delete-orphan")
    responses = relationship("PatientResponse", back_populates="patient", cascade="all, delete-orphan")
    emotions = relationship("EmotionRecord", back_populates="patient", cascade="all, delete-orphan")
    summaries = relationship("MedicalSummary", back_populates="patient", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="patient", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="patient", cascade="all, delete-orphan")


class RobotTask(Base):
    """Clinician-requested ANNA bedside tasks."""
    __tablename__ = "robot_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    assigned_by = Column(String(120), nullable=False)
    task_type = Column(String(50), default="ANNA Health Check", nullable=False)
    instructions = Column(Text, nullable=False, default="")
    priority = Column(String(20), nullable=False, default="normal", index=True)  # normal, urgent
    status = Column(String(20), nullable=False, default="queued", index=True)  # queued, in_progress, completed, failed, cancelled

    assigned_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
    created_at = synonym("assigned_at")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)

    patient = relationship("Patient", back_populates="tasks")
    session = relationship("HealthCheckSession", back_populates="task", uselist=False)


class HealthCheckSession(Base):
    """An execution session of an ANNA checkup on a patient."""
    __tablename__ = "health_check_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    robot_task_id = Column(Integer, ForeignKey("robot_tasks.id"), nullable=True, index=True)
    started_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="completed", nullable=False)

    patient = relationship("Patient", back_populates="sessions")
    task = relationship("RobotTask", back_populates="session")
    vitals = relationship("VitalReading", back_populates="session", cascade="all, delete-orphan")
    responses = relationship("PatientResponse", back_populates="session", cascade="all, delete-orphan")
    emotions = relationship("EmotionRecord", back_populates="session", cascade="all, delete-orphan")
    summary = relationship("MedicalSummary", back_populates="session", uselist=False)


class VitalReading(Base):
    """Timestamped physiological vital readings."""
    __tablename__ = "vital_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("health_check_sessions.id"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    temperature_c = Column(Float, nullable=False)
    pulse_bpm = Column(Float, nullable=False)
    spo2_percent = Column(Float, default=98.0, nullable=False)
    ecg_value = Column(String(50), nullable=True)
    ecg_note = Column(String(255), nullable=True)
    recorded_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
    source = Column(String(50), default="ANNA Robot", nullable=False)
    quality_status = Column(String(50), default="measured", nullable=False)  # measured, simulated, noisy

    patient = relationship("Patient", back_populates="vitals")
    session = relationship("HealthCheckSession", back_populates="vitals")


class PatientResponse(Base):
    """Spoken questionnaire answers given during ANNA visit."""
    __tablename__ = "patient_responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("health_check_sessions.id"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    patient = relationship("Patient", back_populates="responses")
    session = relationship("HealthCheckSession", back_populates="responses")


class EmotionRecord(Base):
    """Facial emotion recognition data captured during interaction."""
    __tablename__ = "emotion_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("health_check_sessions.id"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    emotion = Column(String(50), nullable=False)  # Happy, Sad, Angry, Neutral, Fear, Disgust, Surprise
    confidence = Column(Float, default=0.95, nullable=False)
    detected_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)

    patient = relationship("Patient", back_populates="emotions")
    session = relationship("HealthCheckSession", back_populates="emotions")


class MedicalSummary(Base):
    """AI-generated dual observation and patient summary."""
    __tablename__ = "medical_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("robot_tasks.id"), nullable=True, index=True)
    session_id = Column(Integer, ForeignKey("health_check_sessions.id"), nullable=True, index=True)
    author = Column(String(120), nullable=False, default="ANNA Robot")

    clinical_summary = Column(Text, nullable=False)
    patient_summary = Column(Text, nullable=True)

    # Synonym for backwards compatibility:
    summary = synonym("clinical_summary")

    temperature_c = Column(String(30), nullable=True)
    pulse_bpm = Column(String(30), nullable=True)
    spo2_percent = Column(String(30), nullable=True)
    ecg_note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)

    patient = relationship("Patient", back_populates="summaries")
    session = relationship("HealthCheckSession", back_populates="summary")


class Medication(Base):
    """Doctor prescribed medications."""
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    medicine_name = Column(String(120), nullable=False)
    dosage = Column(String(60), nullable=False)  # e.g. "500 mg"
    frequency = Column(String(60), nullable=False)  # e.g. "Twice daily"
    scheduled_time = Column(String(60), nullable=False)  # e.g. "08:00, 20:00"
    start_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    end_date = Column(DateTime, nullable=True)
    instructions = Column(Text, default="", nullable=False)
    status = Column(String(20), default="active", nullable=False, index=True)  # active, completed, discontinued

    patient = relationship("Patient", back_populates="medications")
    logs = relationship("MedicationLog", back_populates="medication", cascade="all, delete-orphan")


class MedicationLog(Base):
    """Administration history of medications."""
    __tablename__ = "medication_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    medication_id = Column(Integer, ForeignKey("medications.id"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    scheduled_time = Column(DateTime, nullable=False)
    administered_time = Column(DateTime, nullable=True)
    status = Column(String(20), default="administered", nullable=False)  # administered, pending, missed
    dispensing_source = Column(String(60), default="Nurse Station", nullable=False)

    medication = relationship("Medication", back_populates="logs")


class Alert(Base):
    """Clinical alerts and risk signals."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("health_check_sessions.id"), nullable=True)
    alert_type = Column(String(60), nullable=False)  # Vital Threshold, Trend Risk, Electrode Warning, High Stress
    severity = Column(String(20), default="NORMAL", nullable=False, index=True)  # NORMAL, WARNING, URGENT
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(120), nullable=True)
    status = Column(String(20), default="active", nullable=False, index=True)  # active, acknowledged, resolved

    patient = relationship("Patient", back_populates="alerts")


class AuditLog(Base):
    """HIPAA/Compliance audit logs."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String(80), nullable=False, index=True)
    details = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
    ip_address = Column(String(50), nullable=True)
