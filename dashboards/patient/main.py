"""Compatibility entry point for the patient port; APIs run in the central app."""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from backend.app.main import app as central_app

app = FastAPI(title="ANNA - Patient Portal")

@app.get("/")
def root():
    return RedirectResponse("/patient")

app.mount("/", central_app)
