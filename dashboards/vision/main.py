"""Authenticated, read-only proxy for ANNA's live annotated vision feed."""

from __future__ import annotations

import hmac
import os
from typing import Iterator
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from ..common.config import config

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app = FastAPI(title="ANNA - Robot Vision")
app.add_middleware(SessionMiddleware, secret_key=config.session_secret, same_site="lax", https_only=False)


class LoginIn(BaseModel):
    email: str
    password: str


def viewer(request: Request) -> str:
    identity = request.session.get("vision_viewer")
    if not identity:
        raise HTTPException(401, "Please sign in to view the robot camera.")
    return str(identity)


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request):
    if not (hmac.compare_digest(payload.email.strip().lower(), config.clinician_email)
            and hmac.compare_digest(payload.password, config.clinician_password)):
        raise HTTPException(401, "Incorrect email or password.")
    request.session.clear()
    request.session["vision_viewer"] = payload.email.strip().lower()
    return {"email": request.session["vision_viewer"]}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    return {"email": request.session.get("vision_viewer")}


def _robot_feed() -> Iterator[bytes]:
    params = {"token": config.robot_vision_token} if config.robot_vision_token else {}
    separator = "&" if "?" in config.robot_vision_stream_url else "?"
    source_url = config.robot_vision_stream_url + (separator + urlencode(params) if params else "")
    try:
        with urlopen(source_url, timeout=10) as response:
            while chunk := response.read(16_384):
                yield chunk
    except URLError:
        # The page will show a reconnect message and can be retried without
        # exposing the robot URL or token to the browser.
        return


@app.get("/api/vision/stream")
def stream(_: str = Depends(viewer)):
    if not config.robot_vision_stream_url:
        raise HTTPException(503, "Robot vision URL is not configured.")
    return StreamingResponse(
        _robot_feed(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
