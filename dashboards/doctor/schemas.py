from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from typing import Optional, List
import datetime as dt

class PatientSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_name: str
    emotion: Optional[str]
    temperature: Optional[str]
    pulse: Optional[str]
    ecg: Optional[str]
    health_report: Optional[str]
    answers: Optional[dict]
    timestamp: dt.datetime

class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_code: str
    full_name: str
    blood_group: str
    bed_number: Optional[int]

class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    assigned_at: dt.datetime
    is_completed: bool
