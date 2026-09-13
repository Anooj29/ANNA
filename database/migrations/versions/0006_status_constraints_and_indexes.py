"""Status check constraints and audit/notes indexes.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    # Check constraints on status fields
    op.create_check_constraint(
        "ck_robot_tasks_status",
        "robot_tasks",
        "status IN ('queued', 'in_progress', 'completed', 'failed', 'cancelled')"
    )
    op.create_check_constraint(
        "ck_alerts_status",
        "alerts",
        "status IN ('active', 'acknowledged', 'under_review', 'resolved', 'dismissed')"
    )
    op.create_check_constraint(
        "ck_alerts_severity",
        "alerts",
        "severity IN ('NORMAL', 'WARNING', 'URGENT', 'CRITICAL')"
    )
    op.create_check_constraint(
        "ck_patients_status",
        "patients",
        "status IN ('admitted', 'discharged')"
    )
    op.create_check_constraint(
        "ck_medications_status",
        "medications",
        "status IN ('active', 'completed', 'discontinued')"
    )
    op.create_check_constraint(
        "ck_beds_status",
        "beds",
        "status IN ('available', 'occupied', 'maintenance')"
    )

    # Performance and query indexes
    op.create_index(
        "ix_audit_logs_action_timestamp",
        "audit_logs",
        ["action", "timestamp"]
    )
    op.create_index(
        "ix_audit_logs_entity",
        "audit_logs",
        ["entity_type", "entity_id"]
    )
    op.create_index(
        "ix_clinical_notes_patient_created",
        "clinical_notes",
        ["patient_id", "created_at"]
    )


def downgrade():
    raise RuntimeError("Downgrade not supported; restore backup instead.")
