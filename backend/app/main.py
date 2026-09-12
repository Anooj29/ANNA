"""Unified Production-Grade FastAPI Application for ANNA Hospital System."""

from __future__ import annotations

import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from dashboards.common.config import config
from dashboards.common.database import Base, engine
from .api import auth, receptionist, clinician, robot, patient
from .websocket import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("anna.server")

# Ensure database tables exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ANNA — Advanced Neural Nursing Automobile",
    description="Unified Hospital Information & Robot Management System",
    version="2.0.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret,
    same_site="lax",
    https_only=False,
)

# Include API Routers
app.include_router(auth.router)
app.include_router(receptionist.router)
app.include_router(clinician.router)
app.include_router(robot.router)
app.include_router(patient.router)


# Real-time WebSocket Endpoint
@app.websocket("/ws/hospital")
async def websocket_hospital_feed(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Client can send ping / heartbeat
            if data == "ping":
                await websocket.send_text('{"event":"pong"}')
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("WebSocket exception: %s", exc)
        ws_manager.disconnect(websocket)


# Static Assets for Dashboards
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RECEPTION_STATIC = os.path.join(BASE_DIR, "dashboards", "receptionist", "static")
CLINICIAN_STATIC = os.path.join(BASE_DIR, "dashboards", "clinician", "static")
PATIENT_STATIC = os.path.join(BASE_DIR, "dashboards", "patient", "static")

# Mount sub-paths
if os.path.exists(RECEPTION_STATIC):
    app.mount("/receptionist/static", StaticFiles(directory=RECEPTION_STATIC), name="reception_static")

if os.path.exists(CLINICIAN_STATIC):
    app.mount("/clinician/static", StaticFiles(directory=CLINICIAN_STATIC), name="clinician_static")

if os.path.exists(PATIENT_STATIC):
    app.mount("/patient/static", StaticFiles(directory=PATIENT_STATIC), name="patient_static")


@app.get("/receptionist")
def get_receptionist_page():
    return FileResponse(os.path.join(RECEPTION_STATIC, "index.html"))


@app.get("/clinician")
def get_clinician_page():
    return FileResponse(os.path.join(CLINICIAN_STATIC, "index.html"))


@app.get("/patient")
def get_patient_page():
    return FileResponse(os.path.join(PATIENT_STATIC, "index.html"))


# Root Landing Page: Hospital System Hub
@app.get("/")
def get_hub_page():
    hub_html = os.path.join(BASE_DIR, "dashboards", "hub.html")
    if os.path.exists(hub_html):
        return FileResponse(hub_html)
    return HTMLResponse("<h1>ANNA Hospital System</h1><p><a href='/receptionist'>Receptionist</a> | <a href='/clinician'>Clinician</a> | <a href='/patient'>Patient</a></p>")
