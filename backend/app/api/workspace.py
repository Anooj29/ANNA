"""Clinical workspace APIs backed by stored measurements and events."""
from __future__ import annotations

import datetime as dt
import csv
import io
from html import escape
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from dashboards.common.database import get_db
from dashboards.common.config import config
from dashboards.common.models import Alert, AuditLog, ClinicalNote, HealthCheckSession, MedicalSummary, Notification, Patient, RobotTask, RobotStatus, User, VitalReading
from ..auth import require_role
from ..services.patient_attention import assess_patient, patient_contexts, RANK
from ..services.patient_analytics import compare_visits, trend_summary
from ..services.timeline import patient_timeline, patient_timeline_paged

router = APIRouter(prefix="/api", tags=["clinical_workspace"], dependencies=[Depends(require_role("doctor", "nurse", "admin"))])


@router.get("/clinician/notifications")
def notifications(limit: int = Query(30, ge=1, le=100), unread_only: bool = False,
                  user: User = Depends(require_role("doctor", "nurse", "admin")),
                  db: Session = Depends(get_db)):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    unread = query.filter(Notification.read_at.is_(None)).count()
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    rows = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
    return {"unread_count": unread, "items": [{"id": row.id, "event_type": row.event_type,
            "title": row.title, "patient_id": row.patient_id, "alert_id": row.alert_id,
            "task_id": row.task_id, "created_at": row.created_at.isoformat(),
            "read_at": row.read_at.isoformat() if row.read_at else None} for row in rows]}


@router.post("/clinician/notifications/{notification_id}/read")
def read_notification(notification_id: int, user: User = Depends(require_role("doctor", "nurse", "admin")),
                      db: Session = Depends(get_db)):
    row = db.query(Notification).filter(Notification.id == notification_id,
                                        Notification.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if row.read_at is None:
        row.read_at = dt.datetime.utcnow()
        db.commit()
    return {"ok": True}


@router.get("/admin/audit")
def audit_events(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 action: str | None = None, _: User = Depends(require_role("admin")),
                 db: Session = Depends(get_db)):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    total = query.count()
    rows = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "offset": offset, "limit": limit,
            "items": [{"id": row.id, "actor_id": row.user_id, "actor_role": row.actor_role,
                       "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id,
                       "source": row.source, "timestamp": row.timestamp.isoformat(), "details": row.details}
                      for row in rows]}


from ..schemas import AlertTransitionRequest, ClinicalNoteCreate, TimelineResponseModel

NoteCreate = ClinicalNoteCreate
AlertTransition = AlertTransitionRequest


def find_patient(db: Session, code: str) -> Patient:
    patient = db.query(Patient).filter(Patient.patient_code == code.strip().upper()).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return patient


@router.get("/patients/{patient_code}/attention")
def attention(patient_code: str, db: Session = Depends(get_db)):
    return assess_patient(db, find_patient(db, patient_code))


@router.get("/patients/{patient_code}/trends")
def trends(patient_code: str, range: Literal["6h", "24h", "7d", "30d"] = "24h", db: Session = Depends(get_db)):
    return trend_summary(db, find_patient(db, patient_code).id, range)


@router.get("/patients/{patient_code}/changes")
def changes(patient_code: str, db: Session = Depends(get_db)):
    return compare_visits(db, find_patient(db, patient_code).id)


@router.get("/patients/{patient_code}/timeline")
def timeline(
    patient_code: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200),
    event_type: str | None = None,
    db: Session = Depends(get_db),
):
    effective_size = limit if limit is not None else page_size
    return patient_timeline_paged(db, find_patient(db, patient_code), page=page, page_size=effective_size, event_type=event_type)


@router.get("/patients/{patient_code}/notes")
def list_notes(patient_code: str, db: Session = Depends(get_db)):
    patient = find_patient(db, patient_code)
    notes = db.query(ClinicalNote).filter(ClinicalNote.patient_id == patient.id).order_by(ClinicalNote.created_at.desc()).all()
    return [{"id": n.id, "author": n.author_name, "content": n.content, "note_type": n.note_type,
             "created_at": n.created_at.isoformat(), "updated_at": n.updated_at.isoformat()} for n in notes]


@router.post("/patients/{patient_code}/notes", status_code=201)
async def add_note(patient_code: str, payload: NoteCreate, request: Request,
                   user: User = Depends(require_role("doctor", "nurse", "admin")), db: Session = Depends(get_db)):
    patient = find_patient(db, patient_code)
    if payload.related_session_id is not None:
        from dashboards.common.models import HealthCheckSession
        session = db.get(HealthCheckSession, payload.related_session_id)
        if not session or session.patient_id != patient.id:
            raise HTTPException(status_code=422, detail="Related visit does not belong to this patient.")
    note = ClinicalNote(patient_id=patient.id, author_id=user.id, author_name=user.full_name,
                        content=payload.content.strip(), note_type=payload.note_type,
                        related_session_id=payload.related_session_id)
    db.add(note)
    db.flush()
    db.add(AuditLog(user_id=user.id, actor_role=user.role, action="clinical_note_created",
                    entity_type="clinical_note", entity_id=str(note.id), source="web",
                    details=f"Clinical note added to {patient.patient_code}.", timestamp=dt.datetime.utcnow(),
                    ip_address=request.client.host if request.client else None))
    db.commit()
    return {"id": note.id, "created_at": note.created_at.isoformat()}


@router.get("/clinician/priority")
def priority(db: Session = Depends(get_db)):
    patients = db.query(Patient).filter(Patient.status == "admitted").all()
    readings_by_patient, alerts_by_patient = patient_contexts(db, [p.id for p in patients])
    rows = []
    for patient in patients:
        attention_data = assess_patient(db, patient, readings=readings_by_patient[patient.id], alerts=alerts_by_patient[patient.id])
        rows.append({"patient_code": patient.patient_code, "full_name": patient.full_name,
                     "bed_number": patient.bed_number, "attention": attention_data})
    rows.sort(key=lambda row: RANK[row["attention"]["level"]], reverse=True)
    return rows


@router.get("/robot/status")
def robot_status(db: Session = Depends(get_db)):
    now = dt.datetime.utcnow()
    timeout = config.robot_offline_timeout_seconds
    return [{"robot_id": robot.robot_id,
             "status": robot.status if (now - robot.last_seen_at).total_seconds() < timeout else "offline",
             "last_seen_at": robot.last_seen_at.isoformat(), "current_task_id": robot.current_task_id,
             "battery_percent": robot.battery_percent}
            for robot in db.query(RobotStatus).all()]


@router.patch("/alerts/{alert_id}/status")
async def transition_alert(alert_id: int, payload: AlertTransition, request: Request,
                           user: User = Depends(require_role("doctor", "nurse", "admin")), db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    if alert.status in {"resolved", "dismissed"}:
        raise HTTPException(status_code=409, detail="Alert is already closed.")
    if payload.status == "dismissed" and user.role not in {"doctor", "admin"}:
        raise HTTPException(status_code=403, detail="Only a doctor or admin may dismiss an alert.")
    if payload.status == "dismissed" and not payload.note:
        raise HTTPException(status_code=422, detail="A dismissal reason is required.")
    alert.status = payload.status
    alert.resolution_note = payload.note
    if payload.status in {"resolved", "dismissed"}:
        alert.resolved_at = dt.datetime.utcnow()
        alert.resolved_by = user.full_name
    db.add(AuditLog(user_id=user.id, actor_role=user.role, action="alert_status_changed",
                    entity_type="alert", entity_id=str(alert.id), source="web",
                    details=f"Alert #{alert.id} moved to {payload.status}.", timestamp=dt.datetime.utcnow(),
                    ip_address=request.client.host if request.client else None))
    db.commit()
    from ..websocket import ws_manager
    await ws_manager.broadcast("alert_updated", {"alert_id": alert.id, "status": alert.status})
    return {"ok": True, "status": alert.status}


@router.get("/analytics/operations")
def operations(days: int = Query(7, ge=1, le=30), db: Session = Depends(get_db)):
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    tasks = db.query(RobotTask).filter(RobotTask.assigned_at >= since).all()
    completed = [t for t in tasks if t.status == "completed"]
    durations = [(t.completed_at - t.started_at).total_seconds() for t in completed if t.started_at and t.completed_at]
    alerts = db.query(Alert).filter(Alert.created_at >= since).all()
    return {"period_days": days, "total_tasks": len(tasks), "completed_visits": len(completed),
            "failed_visits": sum(t.status == "failed" for t in tasks),
            "completion_rate": round(len(completed) / len(tasks) * 100, 1) if tasks else None,
            "average_visit_seconds": round(sum(durations) / len(durations)) if durations else None,
            "alerts_detected": len(alerts), "patients_monitored": len({t.patient_id for t in completed}),
            "estimated_time_saved_minutes": len(completed) * config.manual_check_minutes,
            "estimate_formula": f"completed_visits × {config.manual_check_minutes} configured manual-check minutes"}


@router.get("/reports/patients/{patient_code}", response_class=HTMLResponse)
def patient_report(patient_code: str, request: Request, days: int = Query(30, ge=1, le=365),
                   user: User = Depends(require_role("doctor", "nurse", "admin")),
                   db: Session = Depends(get_db)):
    patient = find_patient(db, patient_code)
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    visits = db.query(HealthCheckSession).filter(HealthCheckSession.patient_id == patient.id,
                                                HealthCheckSession.started_at >= since).order_by(HealthCheckSession.started_at.desc()).all()
    vitals = db.query(VitalReading).filter(VitalReading.patient_id == patient.id,
                                          VitalReading.recorded_at >= since).order_by(VitalReading.recorded_at.desc()).all()
    alerts = db.query(Alert).filter(Alert.patient_id == patient.id,
                                    Alert.created_at >= since).order_by(Alert.created_at.desc()).all()
    notes = db.query(ClinicalNote).filter(ClinicalNote.patient_id == patient.id,
                                         ClinicalNote.created_at >= since).order_by(ClinicalNote.created_at.desc()).all()
    summaries = db.query(MedicalSummary).filter(MedicalSummary.patient_id == patient.id,
                                                MedicalSummary.created_at >= since).order_by(MedicalSummary.created_at.desc()).all()
    db.add(AuditLog(
        user_id=user.id,
        actor_role=user.role,
        action="patient_report_viewed",
        entity_type="patient",
        entity_id=patient.patient_code,
        source="web",
        details=f"Clinical report generated for {patient.patient_code} ({days} days range).",
        timestamp=dt.datetime.utcnow(),
        ip_address=request.client.host if request.client else None,
    ))
    db.commit()
    def cell(value):
        return escape(str(value)) if value is not None else "Not available"
    def rows(values):
        return "".join("<tr>" + "".join(f"<td>{cell(v)}</td>" for v in row) + "</tr>" for row in values)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ANNA patient report</title>
    <style>body{{font:15px system-ui;max-width:1000px;margin:2rem auto;color:#173142;line-height:1.5}}
    h1,h2{{color:#12666f}}table{{width:100%;border-collapse:collapse;margin-bottom:2rem}}th,td{{border:1px solid #d5e4e8;padding:.5rem;text-align:left}}
    th{{background:#e8f4f5}}small{{color:#526974}}@media print{{button{{display:none}}body{{margin:0}}}}</style></head><body>
    <button onclick="print()">Print or save as PDF</button><h1>ANNA clinical visit report</h1>
    <p><strong>{cell(patient.full_name)}</strong> · {cell(patient.patient_code)} · Bed {cell(patient.bed_number)}<br>
    Reporting period: last {days} days · Generated {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
    <p><small>ANNA is assistive monitoring software. This report does not provide a diagnosis. Simulated readings are identified and must not guide care.</small></p>
    <h2>ANNA visits</h2><table><tr><th>Started</th><th>Completed</th><th>Status</th><th>Task</th></tr>{rows((v.started_at, v.completed_at, v.status, v.robot_task_id) for v in visits)}</table>
    <h2>Measurements and quality</h2><table><tr><th>Time</th><th>Temperature</th><th>Temperature status</th><th>Pulse</th><th>Pulse status</th><th>SpO₂</th><th>SpO₂ status</th><th>Source</th></tr>
    {rows((v.recorded_at, v.temperature_c, v.temperature_status, v.pulse_bpm, v.pulse_status, v.spo2_percent, v.spo2_status, v.source) for v in vitals)}</table>
    <h2>Clinical alerts</h2><table><tr><th>Time</th><th>Severity</th><th>Message</th><th>Status</th></tr>{rows((a.created_at, a.severity, a.message, a.status) for a in alerts)}</table>
    <h2>Clinician notes</h2><table><tr><th>Time</th><th>Author</th><th>Type</th><th>Note</th></tr>{rows((n.created_at, n.author_name, n.note_type, n.content) for n in notes)}</table>
    <h2>ANNA assistive summaries</h2><table><tr><th>Time</th><th>Source</th><th>Summary</th></tr>{rows((s.created_at, s.author, s.clinical_summary) for s in summaries)}</table>
    </body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/reports/operations.csv")
def operations_csv(request: Request, days: int = Query(7, ge=1, le=30),
                   user: User = Depends(require_role("doctor", "nurse", "admin")),
                   db: Session = Depends(get_db)):
    values = operations(days, db)
    db.add(AuditLog(
        user_id=user.id,
        actor_role=user.role,
        action="operations_csv_exported",
        entity_type="operations",
        entity_id=f"{days}d",
        source="web",
        details=f"Operations CSV exported for past {days} days.",
        timestamp=dt.datetime.utcnow(),
        ip_address=request.client.host if request.client else None,
    ))
    db.commit()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    for key, value in values.items():
        writer.writerow([key, value])
    return Response(output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=anna-operations.csv", "Cache-Control": "no-store"})
