# ANNA hospital software audit — 2026-09-13

> Historical audit: this records the repository's state before the SIH 2026
> upgrade. The current hospital software uses PostgreSQL only. See
> `sih_2026_software_upgrade.md` for implementation status.

## Current implementation note — 2026-09-13

The findings below are the pre-upgrade baseline, not the present runtime.
The central FastAPI app now uses PostgreSQL only, Alembic revision 0005,
role-protected routes and WebSockets, hashed patient PINs, and a Windows
`run.bat` launcher. The launcher binds on `0.0.0.0:8000`, prints the current
Wi-Fi URL for phones, and checks for an occupied port before starting.
Phones must use that Wi-Fi URL rather than `127.0.0.1`; Windows Firewall and
guest/client-isolated networks can still block access.

The mobile layout was checked in rendered Chromium at 320, 390, and 768 CSS
pixels after signing in to each profile. Every clinician and receptionist tab
and the patient portal fit the viewport without page-wide horizontal scroll.
The fix removes a shared 720px table minimum that overrode mobile cards,
allows header controls and legends to wrap, keeps tab navigation within its
own horizontal scroller, makes intake form columns collapse correctly, and
contains the directory search field. The patient language picker no longer
overlays the phone header. Further manual checks on physical Android/iOS
devices, including browser zoom and assistive technology, remain open.

## Current architecture

`backend/app/main.py` is the central FastAPI entry point. It includes five routers (`auth`, `receptionist`, `clinician`, `patient`, `robot`), serves the three HTML/CSS/JavaScript dashboards, and hosts `/ws/hospital`. `dashboards/{receptionist,clinician,patient}/main.py` each recreate the full API, CORS, session middleware, and WebSocket on separate ports. All four apps share SQLAlchemy models and engine in `dashboards/common`; configuration is in `dashboards/common/config.py`. SQLite is the local default; Postgres is optional through `docker-compose.yml`. `dashboards/init_db.py` and `database/seed_data.py` create/seed schema; there is no Alembic history. The separate `anna_robot/` package owns hardware, sensors, interaction, and navigation and was not changed in this audit.

Reception handles intake, photos, beds, discharge, and occupancy charts. Clinician handles patient search/profile, vitals, analytics, tasks, alerts, medications, and summaries. Portal uses a patient session for own profile, vitals, history, medications, and trends. Robot API claims tasks and posts results. WebSocket events refresh reception and clinician views. No report-generation API or dedicated clinical-note model was found; `MedicalSummary` is an ANNA assistive summary, not a clinician note.

## Confirmed problems and priority

| Priority | Finding | Location / consequence |
| --- | --- | --- |
| P0 | Reception intake posts `/api/patients/admit` but backend registers at `POST /api/patients` | `dashboards/receptionist/static/app.js`, `backend/app/api/receptionist.py`; admission fails with 404. |
| P0 | Clinical/reception routes have no role dependency; public callers can read patient records, prescribe medications, discharge patients, reset PINs, and create tasks | `backend/app/api/clinician.py`, `receptionist.py`. |
| P0 | Hospital WebSocket accepts anonymous clients and broadcasts patient names/codes | `backend/app/main.py`, the three duplicate `main.py` files, `backend/app/websocket.py`. |
| P0 | Robot completion substitutes 36.8/75/98 on missing or malformed sensors, fabricates ECG and emotion metadata, and the failed-task branch later references undefined vital variables | `backend/app/api/robot.py`. Also `simulate-checkup` is public and writes synthetic records. |
| P0 | PINs are stored in plaintext alongside hashes and legacy plaintext verification remains enabled | `Patient.portal_pin`, registration/reset, `verify_pin`, portal login, patient profile. Existing rows need safe backfill before removing legacy verification. |
| P0 | Default session secret, robot key, Postgres password, bootstrap passwords, and `init_postgres.py` root password are in source/examples; CORS is `*` and cookies are never secure | `dashboards/common/config.py`, `.env.example`, `docker-compose.yml`, `init_postgres.py`, app entry points, `database/seed_data.py`. Rotate any deployed values. |
| P1 | `bcrypt` is imported but missing from dashboard requirements; pytest is absent from the existing virtual environment | `backend/app/auth.py`, `database/seed_data.py`, `requirements-dashboard.txt`. |
| P1 | `VitalReading` requires all three values and defaults SpO2 to 98; only one row-level quality status exists, so partial sensor failure cannot be represented correctly | `dashboards/common/models.py`; needs additive migration before nullable measurements. |
| P1 | Several API/client views label normality without freshness/quality; risk logic reads any latest vital and uses no configurable thresholds | `backend/app/api/{patient,clinician}.py`, dashboard JS. |
| P1 | Reception search receives clinician-level patient data; clinician profile includes `portal_pin` | `GET /api/patients`, `GET /api/patients/{code}`. Split operational and clinical responses. |
| P1 | Duplicate app entry points can drift; `create_all` runs on import; schema and seed scripts are not migration-safe for evolving columns | app entry points, `dashboards/init_db.py`. |
| P2 | Chart and table layouts are independent, use hardcoded colors/copy, and have no shared design tokens | all `dashboards/*/static/{index.html,style.css,app.js}`. |
| P2 | Some schemas are unused/duplicated (`dashboards/*/schemas.py`); `dashboards/receptionist/crud.py` is not part of the central route path; README describes older multi-app topology | repository documentation and dashboard modules. |

## Recommended architecture

Keep `anna_robot/` as a separate client. Make `backend/app/main.py` the one deployment entry point and move reusable hospital logic gradually into `backend/app/services/`. Keep dashboard assets in `dashboards/` and point all three UIs at the same origin/API. Retain the robot's existing task polling and completion paths; any extension must be backward-compatible. Centralize role checks, session security, and WebSocket authorization in `backend/app/auth.py` and the central app. Adopt Alembic against `dashboards/common/models.py` before changing stored columns. Build operational reception responses separately from clinical doctor/nurse responses. Make measurements nullable with explicit per-measurement status and source/time, preserving historical records. Keep simulation visibly demo-only and disabled in production.

## Exact files / migration needs

Initial P0/P1 work: `backend/app/{main.py,auth.py,schemas.py,websocket.py}`, `backend/app/api/{auth,receptionist,clinician,patient,robot}.py`, `dashboards/common/{config,models}.py`, `dashboards/{receptionist,clinician,patient}/main.py`, `dashboards/receptionist/static/app.js`, `dashboards/clinician/static/app.js`, `requirements-dashboard.txt`, `.env.example`, `docker-compose.yml`, `init_postgres.py`, and tests. Later UI work: all three dashboard `static/index.html`, `static/style.css`, `static/app.js`; shared tokens/assets under `dashboards/common/static/` if useful.

Migration requirements: backfill `portal_pin_hash` from legacy `portal_pin` without exposing it; clear plaintext PINs after verified backfill; make vital numeric fields nullable and remove the SpO2 default; add per-measurement status/quality/source fields, indexes, and later alert lifecycle/audit/notes data. These must be additive and tested on a database copy before production; `create_all` cannot alter existing tables. No existing DB contents were modified during this audit.

## Risks

The checked-out `.env` is ignored and was not printed or changed. Existing sample/production SQLite contents are not test fixtures. Separate dashboard processes currently expose all routers, so central-only fixes need to be shared or those entry points retired before network use. Patient PIN backfill needs a deliberate migration and a backup. Current prototype-generated vitals and summaries may look clinical; historical records need provenance labels. Robot API payload compatibility and consent/navigation behavior require validation with the physical robot team.

## Phased implementation checklist

1. **P0 reliability/security:** correct admission URL; prevent fabricated/undefined completion values; require route roles and authenticated WebSockets; restrict demo simulation; remove hardcoded source credentials and plaintext PIN creation; add focused tests.
2. **Data safety:** introduce Alembic, migrate legacy PINs and nullable/quality-aware vital fields, test on a copied DB, then remove legacy plaintext verification.
3. **Backend services:** separate operational/clinical schemas; deterministic attention, alerts, trends, comparison, timeline, analytics; audit coverage, health/readiness, pagination and request validation.
4. **UI foundation:** shared healthcare tokens/components, clear loading/error/empty states, accessibility and responsive behavior.
5. **Workspaces:** clinician priority/alerts/patient profile/task progress; reception occupancy/intake/bed management; patient-safe portal/trends; wire only stored values and events.
6. **Release quality:** independent test DB, CI, dependency validation, migration rehearsal, API/robot compatibility and demo walkthrough.
