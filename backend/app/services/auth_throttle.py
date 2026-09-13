"""Database-backed login throttling shared by staff and patient portal."""
from __future__ import annotations

import datetime as dt
import hashlib

from fastapi import HTTPException
from sqlalchemy.orm import Session

from dashboards.common.models import AuthAttempt

WINDOW = dt.timedelta(minutes=15)
MAX_FAILURES = 5


def _attempt(db: Session, scope: str, identifier: str, ip_address: str):
    digest = hashlib.sha256(identifier.casefold().encode("utf-8")).hexdigest()
    return db.query(AuthAttempt).filter_by(scope=scope, identifier_hash=digest, ip_address=ip_address).first(), digest


def check_login_allowed(db: Session, scope: str, identifier: str, ip_address: str):
    row, _ = _attempt(db, scope, identifier, ip_address)
    now = dt.datetime.utcnow()
    if row and row.blocked_until and row.blocked_until > now:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")


def record_login_failure(db: Session, scope: str, identifier: str, ip_address: str):
    row, digest = _attempt(db, scope, identifier, ip_address)
    now = dt.datetime.utcnow()
    if row is None:
        row = AuthAttempt(scope=scope, identifier_hash=digest, ip_address=ip_address, failures=0, first_failure_at=now)
        db.add(row)
    if now - row.first_failure_at > WINDOW:
        row.failures = 0
        row.first_failure_at = now
    row.failures += 1
    if row.failures >= MAX_FAILURES:
        row.blocked_until = now + WINDOW
    db.commit()


def clear_login_failures(db: Session, scope: str, identifier: str, ip_address: str):
    row, _ = _attempt(db, scope, identifier, ip_address)
    if row:
        db.delete(row)
        db.commit()
