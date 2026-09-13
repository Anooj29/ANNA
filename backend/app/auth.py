"""Authentication, password hashing, and role-based security dependencies."""

from __future__ import annotations

import hmac
import logging
from typing import Optional
import bcrypt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from dashboards.common.config import config
from dashboards.common.database import get_db
from dashboards.common.models import User, Patient

logger = logging.getLogger("anna.auth")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def verify_pin(plain_pin: str, hashed_pin: Optional[str]) -> bool:
    return bool(hashed_pin and verify_password(plain_pin, hashed_pin))


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User session invalid or deactivated.")
    return user


def require_role(*roles: str):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Forbidden. Role '{current_user.role}' lacks permissions.")
        return current_user
    return role_checker


def get_portal_patient(request: Request, db: Session = Depends(get_db)) -> Patient:
    patient_id = request.session.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=401, detail="Patient authentication required.")
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=401, detail="Patient profile not found.")
    return patient


def robot_authorised(x_anna_robot_key: str = Header(default="")) -> None:
    if not config.robot_api_key or not hmac.compare_digest(x_anna_robot_key, config.robot_api_key):
        raise HTTPException(status_code=401, detail="Robot API key authorisation failed.")
