"""Typed birth date and composite indexes for frequent ward queries."""
import datetime as dt

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("patients", sa.Column("birth_date", sa.Date(), nullable=True))
    connection = op.get_bind()
    for patient_id, legacy_date in connection.execute(sa.text(
            "SELECT id, date_of_birth FROM patients WHERE date_of_birth IS NOT NULL")):
        try:
            parsed = dt.date.fromisoformat(legacy_date)
        except (TypeError, ValueError):
            continue  # Preserve the original text for manual correction.
        connection.execute(sa.text("UPDATE patients SET birth_date=:date WHERE id=:id"),
                           {"date": parsed, "id": patient_id})
    op.create_index("ix_vital_readings_patient_recorded_at", "vital_readings", ["patient_id", "recorded_at"])
    op.create_index("ix_alerts_patient_created_at", "alerts", ["patient_id", "created_at"])
    op.create_index("ix_robot_tasks_status_assigned_at", "robot_tasks", ["status", "assigned_at"])


def downgrade():
    raise RuntimeError("Downgrade would remove typed patient data and indexes; restore a backup instead.")
