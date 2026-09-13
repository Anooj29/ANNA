"""Doctor dashboard: manages patient assignments and reviews health reports."""

from __future__ import annotations

import logging
import os
import socket
import json

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from ..common.config import config
from ..common.database import get_db
from ..common.models import Patient
from . import crud
from .schemas import PatientOut, PatientSessionOut, AssignmentOut

logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="ANNA - Doctor Dashboard")

def send_robot_command(command: dict):
    """Sends a JSON command to the robot's TCP port."""
    try:
        # In a real deployment, ROBOT_HOST would be in config
        robot_host = os.environ.get("ROBOT_HOST", "localhost")
        robot_port = int(os.environ.get("ROBOT_TCP_PORT", 5000))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect((robot_host, robot_port))
            s.sendall((json.dumps(command) + "\n").encode("utf-8"))
            logger.info("Sent command to robot: %s", command)
    except Exception as e:
        logger.error("Failed to send command to robot: %s", e)

@app.get("/api/patients", response_model=list[PatientOut])
def get_patients(db: Session = Depends(get_db)):
    return crud.list_patients(db)

@app.get("/api/patients/{patient_name}/sessions", response_model=list[PatientSessionOut])
def get_sessions(patient_name: str, db: Session = Depends(get_db)):
    return crud.get_patient_sessions(db, patient_name)

@app.post("/api/assignments", response_model=AssignmentOut)
def assign_patient(patient_id: int, db: Session = Depends(get_db)):
    try:
        assignment = crud.create_assignment(db, patient_id)

        # Also send the command to the robot
        patient = db.get(Patient, patient_id)
        if patient:
            send_robot_command({
                "command": "navigate_to",
                "target": patient.full_name
            })

        return assignment
    except Exception as e:
        logger.exception("Failed to create assignment")
        raise HTTPException(500, str(e))

# Serve static frontend
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
