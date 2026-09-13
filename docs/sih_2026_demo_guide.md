# ANNA — SIH 2026 Demonstration Guide

**Project**: ANNA — Advanced Neural Nursing Automobile  
**Platform**: Unified Hospital Information System & AI Mobile Assistant  
**Database**: PostgreSQL 18.6 with Alembic Versioning (Revision 0006)  

---

## 1. System Overview & Architecture

ANNA connects hospital staff, admitted patients, and autonomous bedside nursing robots through a single centralized FastAPI application and a shared PostgreSQL database.

### User Roles & Endpoints
1. **Hospital Reception (`/receptionist`)**:
   - Patient admission with photo registration, demographics, and immediate bed assignment.
   - Bed management grid (General, ICU, Step-Down) across Ward A and Ward B.
   - Patient discharge with automatic bed release and timestamping.
   - Privacy-safe directory: clinical notes and detailed vital histories are strictly hidden.
2. **Clinician / Doctor Dashboard (`/clinician`)**:
   - Ward Attention Roster: Deterministic attention scoring (`CRITICAL`, `URGENT`, `REVIEW`, `OBSERVE`, `STABLE`) based on vitals breaches and alerts.
   - Patient Clinical Workspace:
     - Quality-Aware Vitals (`measured`, `poor_signal`, `sensor_error`, `invalid`).
     - "What Changed Since Previous Visit?": Exact parameter deltas between reliable visits.
     - Interactive Trend Charts: 6h, 24h, 7d, 30d time ranges excluding corrupted sensor readings.
     - Chronological Timeline: Paginated with event type filters (`ALERT`, `ANNA`, `ADMISSION`, `CLINICAL_NOTE`).
     - Clinical Progress Notes: Role-stamped, audit-logged notes with session linkages.
     - Clinical Alerts Workspace: Lifecycle transitions (`Active` -> `Under Review` -> `Resolved` / `Dismissed` with mandatory clinician reason).
     - Task Orchestration: Queuing bedside checkups with priority (`Normal` vs `Urgent`).
     - Operations & Impact Analytics: Real-time visit counts, duration averages, time-saved estimates.
     - Dual Observations & Reports: Side-by-side formal clinical observations vs plain-language patient summaries. Printable PDF-ready clinical reports and operations CSV export.
3. **Patient Care Portal (`/patient`)**:
   - Authenticated with 6-digit hashed PIN and Patient Code.
   - Strict isolation: Patients can only view their own data.
   - Multilingual Support: Switch dynamically between **English**, **Hindi (हिंदी)**, and **Marathi (मराठी)**.
   - Plain-Language Summaries: Understandable explanations of robot rounds without medical jargon.
   - Prescribed Medications: Structured schedule times (e.g. 08:00, 20:00) and instructions.
4. **Robot Gateway (`/api/robot/*`)**:
   - Secure header authentication (`X-ANNA-Robot-Key`).
   - Priority Task Dispatch with PostgreSQL row locking (`with_for_update(skip_locked=True)`).
   - Real-time Stage Progression (`Navigating`, `Aligning`, `Measuring Vitals`, `Summary`).
   - Heartbeat with automatic offline detection.

---

## 2. Step-by-Step Live Demonstration Walkthrough

### Step 1: Pre-Demo Database Setup
Ensure PostgreSQL is running and seed the deterministic demonstration dataset:
```bash
# Set passwords for staff accounts
set SEED_DOCTOR_PASSWORD=DoctorPass2026!
set SEED_RECEPTION_PASSWORD=ReceptionPass2026!
set SEED_PATIENT_PIN=123456

# Run seed script
.venv-dashboard\Scripts\python.exe -m database.seed_data
```

### Step 2: Start the Central Application
```bash
run.bat
```
The server binds to `0.0.0.0:8000`. Navigate to `http://localhost:8000/`.

### Step 3: Receptionist Workflow (3 minutes)
1. Navigate to `/receptionist` and log in with `reception` / `ReceptionPass2026!`.
2. Inspect the **Ward Bed Grid**: Show available vs occupied beds across Ward A and Ward B.
3. Click **Admit Patient**:
   - Enter Name: "Aarav Mehta", Age: 42, Blood Group: "B+", Bed: Bed 4.
   - Upload reference photo for facial recognition enrollment.
   - Note the generated Patient ID (e.g. `ANP-00013`) and 6-digit Portal Access PIN.
4. Show that patient information immediately appears in the directory without exposing private clinical notes.

### Step 4: Clinician Workflow (5 minutes)
1. Navigate to `/clinician` and log in with `doctor` / `DoctorPass2026!`.
2. Review the **Priority Roster**:
   - Highlight deterministic attention levels (Patients flagged `URGENT` appear at the top).
3. Open Patient Workspace for an urgent patient:
   - **Quality-Aware Vitals**: Point out quality status tags (`measured` vs `poor_signal`). Emphasize that noisy or simulated signals never trigger false clinical alarms.
   - **What Changed?**: Point out the comparison delta panel showing parameter changes from the prior visit.
   - **Vital Trends**: Toggle between 6h, 24h, and 7d ranges.
   - **Timeline**: Show the paginated event history and filter by `ALERT` or `ANNA`.
   - **Add Clinical Note**: Add a progress note ("Patient vitals improving post-medication").
4. **Alerts Lifecycle**:
   - Click an active alert.
   - Select "Under Review" to flag nursing attention.
   - Enter a resolution note and mark "Resolved".
5. **Queue an ANNA Bedside Checkup**:
   - Select task priority `Urgent`, add instructions "Check SpO2 and temperature", and click Dispatch.

### Step 5: Patient Care Portal Walkthrough (3 minutes)
1. Open an Incognito window or navigate to `/patient`.
2. Log in using Patient Code `ANP-00001` and PIN `123456`.
3. Highlight **Multilingual Switcher**:
   - Switch language to **Hindi (हिंदी)**: All headings, vital cards, and empty states switch to Hindi.
   - Switch language to **Marathi (मराठी)**: View Marathi translated interface.
4. Review **Plain-Language Summary**: Emphasize how ANNA translates technical clinical data into patient-friendly advice.
5. Review **Prescribed Medications**: Show 24-hour scheduled dosing times.

### Step 6: Operations & Audit Compliance (2 minutes)
1. In the Clinician Dashboard, navigate to **Reports & Operations**:
   - Click **Print or Save as PDF** to show the formal printable clinical visit report.
   - Click **Export Operations CSV** to download hospital throughput statistics.
2. In the Admin view (`/api/admin/audit`), demonstrate the immutable HIPAA-compliant audit trail recording every login, report export, alert transition, and bed movement.

---

## 3. SIH 2026 Evaluation Criteria Alignment

| SIH Evaluation Criteria | ANNA Implementation |
|---|---|
| **Healthcare Innovation** | Mobile autonomous nursing assistant reducing routine workload by an estimated 10 minutes per patient checkup. |
| **Robust Engineering** | PostgreSQL 18.6 transactional runtime, Alembic migration pipeline, row-locking concurrency, and zero SQLite dependencies. |
| **Clinical Safety** | Quality-aware vital metrics distinguishing reliable measurements from poor signal; deterministic threshold rules preventing alarm fatigue. |
| **Patient-Centric Design** | PIN-isolated patient portal with trilingual support (EN/HI/MR) and AI dual-summarization (clinical vs layman). |
| **Compliance & Governance** | End-to-end audit logging, RBAC security, bcrypt password/PIN hashing, and no-store report caching. |
