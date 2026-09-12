from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    email: str
    password: str


class TaskIn(BaseModel):
    patient_code: str
    task_type: str = Field(pattern="^(health_check|rounding|video_call|medication_reminder)$")
    instructions: str = Field(default="", max_length=1200)
    priority: str = Field(default="normal", pattern="^(routine|normal|urgent)$")


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_code: str
    patient_name: str
    bed_number: Optional[int]
    task_type: str
    instructions: str
    priority: str
    status: str
    assigned_by: str
    created_at: dt.datetime
    started_at: Optional[dt.datetime] = None
    completed_at: Optional[dt.datetime] = None
    failure_reason: Optional[str] = None


class PatientOut(BaseModel):
    patient_code: str
    full_name: str
    bed_number: int
    blood_group: str
    height_cm: float
    weight_kg: float
    registered_at: dt.datetime
    discharged_at: Optional[dt.datetime] = None


class SummaryOut(BaseModel):
    id: int
    patient_code: str
    patient_name: str
    bed_number: Optional[int]
    author: str
    clinical_summary: str
    patient_summary: Optional[str]
    temperature_c: Optional[str]
    pulse_bpm: Optional[str]
    ecg_note: Optional[str]
    created_at: dt.datetime


class RobotCompleteIn(BaseModel):
    status: str = Field(pattern="^(completed|failed)$")
    # ``summary`` remains accepted for old robot clients; new clients send
    # both views explicitly.
    summary: str = Field(default="", max_length=5000)
    clinical_summary: str = Field(default="", max_length=5000)
    patient_summary: str = Field(default="", max_length=5000)
    temperature_c: Optional[str] = Field(default=None, max_length=30)
    pulse_bpm: Optional[str] = Field(default=None, max_length=30)
    ecg_note: Optional[str] = Field(default=None, max_length=255)
    failure_reason: Optional[str] = Field(default=None, max_length=1000)
