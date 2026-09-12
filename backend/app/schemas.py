"""Pydantic validation schemas for ANNA Hospital API."""

from __future__ import annotations

import datetime as dt
from typing import List, Optional
from pydantic import BaseModel, Field


# Auth Schemas
class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class PortalLoginRequest(BaseModel):
    patient_code: str
    portal_pin: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    full_name: str


# Bed Schemas
class BedResponse(BaseModel):
    id: int
    bed_number: int
    ward: str
    bed_type: str
    is_occupied: bool
    status: str
    occupant_code: Optional[str] = None
    occupant_name: Optional[str] = None
    admitted_at: Optional[dt.datetime] = None


# Patient Schemas
class PatientCreateRequest(BaseModel):
    full_name: str
    date_of_birth: Optional[str] = None
    gender: str = "Unspecified"
    blood_group: str
    height_cm: float
    weight_kg: float
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    address: Optional[str] = None
    bed_number: int


class PatientResponseModel(BaseModel):
    id: int
    patient_code: str
    full_name: str
    date_of_birth: Optional[str] = None
    gender: str
    blood_group: str
    height_cm: float
    weight_kg: float
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    address: Optional[str] = None
    photo_path: str
    bed_number: Optional[int] = None
    admission_date: dt.datetime
    discharge_date: Optional[dt.datetime] = None
    status: str
    portal_pin: Optional[str] = None
    latest_vitals: Optional[dict] = None
    risk_level: Optional[str] = "NORMAL"


# Task Schemas
class TaskCreateRequest(BaseModel):
    patient_code: str
    task_type: str = "ANNA Health Check"
    instructions: str = ""
    priority: str = "normal"  # normal, urgent


class TaskResponseModel(BaseModel):
    id: int
    patient_code: str
    patient_name: str
    bed_number: Optional[int] = None
    task_type: str
    instructions: str
    priority: str
    status: str
    assigned_by: str
    assigned_at: dt.datetime
    started_at: Optional[dt.datetime] = None
    completed_at: Optional[dt.datetime] = None
    failure_reason: Optional[str] = None


# Robot Communication Schemas
class RobotCompleteRequest(BaseModel):
    status: str = "completed"
    temperature_c: Optional[str] = None
    pulse_bpm: Optional[str] = None
    spo2_percent: Optional[str] = "98.0"
    ecg_note: Optional[str] = None
    emotion: Optional[str] = "Neutral"
    answers: Optional[dict] = None
    clinical_summary: Optional[str] = None
    patient_summary: Optional[str] = None
    summary: Optional[str] = None  # fallback compatibility
    failure_reason: Optional[str] = None


# Alert Schemas
class AlertResponseModel(BaseModel):
    id: int
    patient_id: int
    patient_code: str
    patient_name: str
    bed_number: Optional[int] = None
    alert_type: str
    severity: str
    message: str
    status: str
    created_at: dt.datetime
    acknowledged_at: Optional[dt.datetime] = None
    acknowledged_by: Optional[str] = None


class AlertAcknowledgeRequest(BaseModel):
    note: Optional[str] = None


# Medication Schemas
class MedicationCreateRequest(BaseModel):
    medicine_name: str
    dosage: str
    frequency: str
    scheduled_time: str
    instructions: str = ""


class MedicationResponseModel(BaseModel):
    id: int
    medicine_name: str
    dosage: str
    frequency: str
    scheduled_time: str
    instructions: str
    status: str
    start_date: dt.datetime
