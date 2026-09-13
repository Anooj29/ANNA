"""ANNA hospital dashboards.

Three planned dashboards share one Postgres database:

- receptionist/  -- registers patients, assigns patient ID + bed (this one)
- clinician/      -- doctor/nurse task assignment for the robot (not built yet)
- patient/        -- patient-facing report viewer (not built yet)

common/ holds the SQLAlchemy models and config shared by all three, so
dashboards 2 and 3 can be added later without touching this package.
"""
