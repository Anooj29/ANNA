"""Unified Production-Grade FastAPI Application for ANNA Hospital System."""

from __future__ import annotations

import logging
import os
import json
import time
import uuid
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from dashboards.common.config import config
from .api import auth, receptionist, clinician, robot, patient, workspace
from .websocket import ws_manager
from .security import check_browser_write, websocket_origin_allowed
from sqlalchemy import text as sql_text
from dashboards.common.database import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("anna.server")

if not config.session_secret:
    raise RuntimeError("DASHBOARD_SESSION_SECRET must be configured before starting ANNA.")

app = FastAPI(
    title="ANNA — Advanced Neural Nursing Automobile",
    description="Unified Hospital Information & Robot Management System",
    version="2.0.0",
)


@app.middleware("http")
async def browser_write_guard(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        check_browser_write(request)
    except HTTPException as exc:
        response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    else:
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(json.dumps({"event": "http_request", "request_id": request_id,
                            "route": request.url.path, "method": request.method,
                            "status": response.status_code,
                            "duration_ms": round((time.perf_counter() - started) * 1000, 1)}))
    return response

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret,
    same_site="lax",
    https_only=config.secure_cookies,
)

# Include API Routers
app.include_router(auth.router)
app.include_router(receptionist.router)
app.include_router(clinician.router)
app.include_router(robot.router)
app.include_router(patient.router)
app.include_router(workspace.router)


@app.get("/api/health")
def health():
    return {"backend": "ok", "version": app.version, "websocket_clients": len(ws_manager.active_connections)}


@app.get("/api/ready")
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(sql_text("SELECT 1"))
            revision = conn.execute(sql_text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if revision != "0006":
            return JSONResponse(status_code=503, content={"backend": "ok", "database": "migration_required", "revision": revision})
        return {"backend": "ok", "database": "ok", "revision": revision, "websocket": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"backend": "ok", "database": "unavailable"})


@app.get("/api/capabilities")
def capabilities():
    return {"demo_simulation": config.enable_demo_simulation}


# Real-time WebSocket Endpoint
@app.websocket("/ws/hospital")
async def websocket_hospital_feed(websocket: WebSocket):
    if not websocket_origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    # SessionMiddleware exposes the signed cookie in the WebSocket scope.
    user_id = websocket.session.get("user_id")
    if not user_id:
        await websocket.close(code=1008)
        return
    from dashboards.common.database import SessionLocal
    from dashboards.common.models import User
    with SessionLocal() as db:
        user = db.get(User, user_id)
        role = user.role if user and user.is_active else None
    if role not in {"admin", "doctor", "nurse", "receptionist"}:
        await websocket.close(code=1008)
        return
    await ws_manager.connect(websocket, role)
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
SHARED_STATIC = os.path.join(BASE_DIR, "dashboards", "common", "static")

# Mount sub-paths
if os.path.exists(RECEPTION_STATIC):
    app.mount("/receptionist/static", StaticFiles(directory=RECEPTION_STATIC), name="reception_static")

if os.path.exists(CLINICIAN_STATIC):
    app.mount("/clinician/static", StaticFiles(directory=CLINICIAN_STATIC), name="clinician_static")

if os.path.exists(PATIENT_STATIC):
    app.mount("/patient/static", StaticFiles(directory=PATIENT_STATIC), name="patient_static")
if os.path.exists(SHARED_STATIC):
    app.mount("/shared/static", StaticFiles(directory=SHARED_STATIC), name="shared_static")


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
