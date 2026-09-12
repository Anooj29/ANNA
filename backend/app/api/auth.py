"""Authentication API routes."""

from __future__ import annotations

import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from dashboards.common.database import get_db
from dashboards.common.models import User, Patient, AuditLog
from ..auth import verify_password, verify_pin, get_current_user, get_portal_patient
from ..schemas import LoginRequest, PortalLoginRequest, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    identifier = payload.username_or_email.strip().lower()
    user = (
        db.query(User)
        .filter((User.username.ilike(identifier)) | (User.email.ilike(identifier)))
        .first()
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username/email or password.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated.")

    # Record login
    user.last_login = dt.datetime.utcnow()
    request.session["user_id"] = user.id
    request.session["user_role"] = user.role
    request.session["user_name"] = user.full_name
    # For backwards compatibility with original clinician session:
    request.session["clinician"] = user.email

    db.add(
        AuditLog(
            user_id=user.id,
            action="login",
            details=f"User {user.username} ({user.role}) logged in successfully.",
            timestamp=dt.datetime.utcnow(),
            ip_address=request.client.host if request.client else "127.0.0.1",
        )
    )
    db.commit()

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        full_name=user.full_name,
    )


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        db.add(
            AuditLog(
                user_id=user_id,
                action="logout",
                details="User logged out.",
                timestamp=dt.datetime.utcnow(),
                ip_address=request.client.host if request.client else "127.0.0.1",
            )
        )
        db.commit()
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return {
                "authenticated": True,
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "full_name": user.full_name,
            }

    # Backward compatibility with original clinician check:
    clinician_email = request.session.get("clinician")
    if clinician_email:
        user = db.query(User).filter(User.email == clinician_email).first()
        if user:
            return {
                "authenticated": True,
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "full_name": user.full_name,
            }
        return {"authenticated": True, "email": clinician_email, "role": "doctor"}

    return {"authenticated": False}
