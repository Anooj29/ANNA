"""ANNA hospital dashboards.

Three planned dashboards share one Postgres database:

- receptionist/  -- registers patients, assigns patient ID + bed (this one)
- clinician/      -- authenticated doctor/nurse task assignment and summaries
- patient/        -- private patient-facing ANNA history portal

common/ holds the SQLAlchemy models and config shared by all three, so
all dashboards can evolve without touching this package.
"""
