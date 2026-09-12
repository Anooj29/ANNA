"""Clinician Command Dashboard application."""

from __future__ import annotations

import os
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from dashboards.common.config import config
from dashboards.common.database import Base, engine
from backend.app.api import auth, receptionist, clinician, robot, patient
from backend.app.websocket import ws_manager

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="ANNA - Clinician Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret,
    same_site="lax",
    https_only=False,
)

# API Routers
app.include_router(auth.router)
app.include_router(receptionist.router)
app.include_router(clinician.router)
app.include_router(robot.router)
app.include_router(patient.router)


@app.websocket("/ws/hospital")
async def ws_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"event":"pong"}')
    except Exception:
        ws_manager.disconnect(websocket)


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
