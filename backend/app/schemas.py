"""Pydantic validation schemas for ANNA Hospital API."""

from __future__ import annotations

import datetime as dt
from typing import List, Literal, Optional
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
    photo_path: Optional[str] = None
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
    robot_id: Optional[str] = None
    current_stage: Optional[str] = None
    stage_updated_at: Optional[dt.datetime] = None


# Robot Communication Schemas
class RobotCompleteRequest(BaseModel):
    status: Literal["completed", "failed"] = "completed"
    temperature_c: Optional[str] = None
    pulse_bpm: Optional[str] = None
    spo2_percent: Optional[str] = None
    temperature_status: Optional[Literal["measured", "poor_signal", "sensor_error", "invalid", "not_available"]] = None
    pulse_status: Optional[Literal["measured", "poor_signal", "sensor_error", "invalid", "not_available"]] = None
    spo2_status: Optional[Literal["measured", "poor_signal", "sensor_error", "invalid", "not_available"]] = None
    temperature_quality: Optional[float] = Field(default=None, ge=0, le=100)
    pulse_quality: Optional[float] = Field(default=None, ge=0, le=100)
    spo2_quality: Optional[float] = Field(default=None, ge=0, le=100)
    robot_id: Optional[str] = Field(default=None, max_length=80)
    ecg_note: Optional[str] = None
    emotion: Optional[str] = None
    emotion_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    answers: Optional[dict] = None
    clinical_summary: Optional[str] = None
    patient_summary: Optional[str] = None
    summary: Optional[str] = None  # fallback compatibility
    failure_reason: Optional[str] = None


class RobotProgressRequest(BaseModel):
    stage: str = Field(min_length=1, max_length=100)
    robot_id: Optional[str] = Field(default=None, max_length=80)


class RobotHeartbeatRequest(BaseModel):
    robot_id: str = Field(min_length=1, max_length=80)
    status: Literal["online", "busy", "unavailable"] = "online"
    current_task_id: Optional[int] = None
    battery_percent: Optional[float] = Field(default=None, ge=0, le=100)
    detail: Optional[str] = Field(default=None, max_length=255)


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
    metric: Optional[str] = None
    actual_value: Optional[float] = None
    threshold_value: Optional[float] = None
    previous_value: Optional[float] = None
    delta: Optional[float] = None
    source: Optional[str] = None
    resolved_at: Optional[dt.datetime] = None
    resolved_by: Optional[str] = None


class AlertAcknowledgeRequest(BaseModel):
    note: Optional[str] = None


# Medication Schemas
class MedicationCreateRequest(BaseModel):
    medicine_name: str
    dosage: str
    frequency: str
    scheduled_time: str = ""
    schedule_times: Optional[List[str]] = None
    instructions: str = ""


class MedicationResponseModel(BaseModel):
    id: int
    medicine_name: str
    dosage: str
    frequency: str
    scheduled_time: str
    schedule_times: Optional[List[str]] = None
    instructions: str
    status: str
    start_date: dt.datetime
