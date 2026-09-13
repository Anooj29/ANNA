"""Compatibility entry point for the clinician port; APIs run in the central app."""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from backend.app.main import app as central_app

app = FastAPI(title="ANNA - Clinician Dashboard")

@app.get("/")
def root():
    return RedirectResponse("/clinician")

app.mount("/", central_app)
