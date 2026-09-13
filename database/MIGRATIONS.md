# ANNA PostgreSQL migrations

PostgreSQL is the only supported hospital software database. Configure
`DB_ENGINE=postgres` and `POSTGRES_*` in `.env` before starting the app.
The robot package remains independent.

For a new empty PostgreSQL database, `run.bat` applies Alembic migrations,
seeds the configured bed capacity, and starts the central API. The equivalent
manual command is `.venv-dashboard\Scripts\python.exe -m dashboards.init_db`.

For an existing unversioned ANNA PostgreSQL database, first make a verified
backup and rehearse the migration on a restored copy. The helper performs
both steps, compares core table row counts, and leaves the source unchanged
unless `--apply` is supplied:

```powershell
.venv-dashboard\Scripts\python.exe -m database.upgrade_existing
.venv-dashboard\Scripts\python.exe -m database.upgrade_existing --apply
```

Backups are written to `~/ANNA-backups` as PostgreSQL custom-format dumps.
Keep them outside the repository and protect them as patient data. If any
patient has a plaintext-only portal PIN, run
`.venv-dashboard\Scripts\python.exe -m database.backfill_portal_pin_hashes`
after making a backup, then rerun the helper. Migration 0002 clears plaintext
PIN values only after checking hashes. Revisions 0002–0004 add measurement
quality, clinical notes and alerts, robot status, notifications, and structured
medication schedules and typed patient birth dates (revision 0005). Historical medication schedule text is retained when it
cannot be parsed safely. Downgrades are intentionally disabled; restore a
verified backup for rollback.

Do not run `database.seed_data` against a populated database. The demo seed
requires an empty PostgreSQL schema and credentials supplied through
`SEED_DOCTOR_PASSWORD`, `SEED_RECEPTION_PASSWORD`, and `SEED_PATIENT_PIN`.
