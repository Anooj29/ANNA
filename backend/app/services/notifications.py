"""Persist staff notifications within the same transaction as their event."""
from sqlalchemy.orm import Session

from dashboards.common.models import Notification, User


def notify_clinicians(db: Session, *, event_type: str, title: str,
                      patient_id: int | None = None, alert_id: int | None = None,
                      task_id: int | None = None) -> None:
    recipients = db.query(User.id).filter(User.is_active.is_(True),
                                          User.role.in_(["doctor", "nurse", "admin"])).all()
    for (user_id,) in recipients:
        db.add(Notification(user_id=user_id, patient_id=patient_id, alert_id=alert_id,
                            task_id=task_id, event_type=event_type, title=title))
