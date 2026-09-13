"""Structured medication schedule and prescriber provenance."""
import datetime as dt

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("medications", sa.Column("schedule_times", sa.JSON(), nullable=True))
    op.add_column("medications", sa.Column("prescriber_id", sa.Integer(), nullable=True))
    op.add_column("medications", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_medications_prescriber_id", "medications", "users", ["prescriber_id"], ["id"])
    op.create_index("ix_medications_prescriber_id", "medications", ["prescriber_id"])
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, scheduled_time FROM medications")).all()
    update = sa.text("UPDATE medications SET schedule_times=:schedule WHERE id=:id").bindparams(
        sa.bindparam("schedule", type_=sa.JSON()))
    for row in rows:
        times = [part.strip() for part in (row.scheduled_time or "").split(",")]
        try:
            if times and all(dt.time.fromisoformat(part).strftime("%H:%M") == part for part in times):
                connection.execute(update, {"schedule": times, "id": row.id})
        except ValueError:
            pass  # Keep unrecognized legacy schedule text visible for clinical review.
    connection.execute(sa.text("UPDATE medications SET created_at = start_date WHERE created_at IS NULL"))


def downgrade():
    raise RuntimeError("Downgrade would remove medication provenance; restore a backup instead.")
