from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bed_number: int
    is_occupied: bool
    occupant_code: Optional[str] = None
    occupant_name: Optional[str] = None
    admitted_at: Optional[dt.datetime] = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_code: str
    full_name: str
    blood_group: str
    height_cm: float
    weight_kg: float
    bed_number: Optional[int]
    photo_path: str
    registered_at: dt.datetime
    discharged_at: Optional[dt.datetime] = None
    portal_pin: Optional[str] = None


class PhotoCheckOut(BaseModel):
    ok: bool
    message: str
