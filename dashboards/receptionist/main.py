"""Compatibility entry point for the reception port; APIs run in the central app."""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from backend.app.main import app as central_app

app = FastAPI(title="ANNA - Receptionist Dashboard")

@app.get("/")
def root():
    return RedirectResponse("/receptionist")

app.mount("/", central_app)
