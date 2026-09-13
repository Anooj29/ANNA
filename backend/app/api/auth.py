"""Authentication API routes."""

from __future__ import annotations

import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from dashboards.common.database import get_db
from dashboards.common.models import User, Patient, AuditLog
from ..auth import verify_password, verify_pin, get_current_user, get_portal_patient
from ..schemas import LoginRequest, PortalLoginRequest, UserResponse
from ..services.auth_throttle import check_login_allowed, record_login_failure, clear_login_failures

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    identifier = payload.username_or_email.strip().lower()
    ip = request.client.host if request.client else "unknown"
    check_login_allowed(db, "staff", identifier, ip)
    user = (
        db.query(User)
        .filter((User.username.ilike(identifier)) | (User.email.ilike(identifier)))
        .first()
    )
    if not user or not verify_password(payload.password, user.password_hash):
        record_login_failure(db, "staff", identifier, ip)
        raise HTTPException(status_code=401, detail="Invalid username/email or password.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated.")
    clear_login_failures(db, "staff", identifier, ip)

    # Record login
    user.last_login = dt.datetime.utcnow()
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["user_role"] = user.role
    request.session["user_name"] = user.full_name

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
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        if user:
            return {
                "authenticated": True,
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "full_name": user.full_name,
            }

    return {"authenticated": False}
