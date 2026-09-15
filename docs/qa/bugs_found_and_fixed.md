# ANNA SIH 2026 — Bugs Discovered & Fixed During Comprehensive QA

This document logs the defects, runtime bugs, and environmental vulnerabilities identified during independent hands-on inspection, live automated browser runs, concurrency testing, and security evaluations of the ANNA Healthcare System.

---

## 1. Defect: Uncaught `ReferenceError: Chart is not defined` in Airgapped / Offline Hospital Environments

- **Component**: Frontend Dashboards (`dashboards/receptionist`, `dashboards/clinician`, `dashboards/patient`)
- **Severity**: High (Presentation & Deployment Blocker)
- **Description**: All three dashboards relied solely on an external CDN URL (`<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>`). In an airgapped hospital network, secure intranet, or firewall-restricted environment (including standard headless test runners and SIH stage evaluation setups), the external CDN was blocked (`net::ERR_NAME_NOT_RESOLVED`). When users switched to the Analytics tabs, `new Chart(...)` threw an unhandled `ReferenceError: Chart is not defined`, crashing the tab rendering and breaking analytics visualization.
- **Resolution**:
  1. Created a self-contained, zero-dependency offline Canvas charting engine in `dashboards/common/static/chart-local.js` that implements the Chart.js compatibility API (`type: 'doughnut'`, `'bar'`, `'line'`, with `.destroy()` and `.update()`).
  2. Mounted and served via `/shared/static/chart-local.js`.
  3. Added the fallback script tag `<script src="/shared/static/chart-local.js"></script>` across all three dashboard templates (`dashboards/receptionist/static/index.html`, `dashboards/clinician/static/index.html`, `dashboards/patient/static/index.html`).
- **Verification**: Verified via Playwright automation. Analytics tabs across Receptionist, Clinician, and Patient dashboards now render cleanly with 0 console errors and 0 page exceptions even with external network access completely disabled.

---

## 2. Defect: Missing Patient Workspace DOM Navigation Trigger

- **Component**: Clinician Dashboard Playwright Automation & DOM Target
- **Severity**: Medium
- **Description**: The patient table rows rendered three action buttons: `.patient-analytics-action`, `.patient-open-action`, and `.patient-task-action`. The initial test query targeted `.btn`, which matched the Analytics modal trigger rather than `.patient-open-action`. As a result, the primary Patient Workspace (`#workspace-content`) was not populated during table navigation.
- **Resolution**: Updated `tests/browser_qa.py` to explicitly target `.patient-open-action`, wait for `#workspace-content` visibility, and verify vitals cards, historical trends, and patient timeline.
- **Verification**: Screenshots `12_clinician_patient_profile.png`, `13_clinician_vitals.png`, `14_clinician_trends.png`, and `15_clinician_timeline.png` successfully captured full workspace state.

---

## 3. Defect: Missing `assigned_by` Constraint in Concurrent Robot Task Creation

- **Component**: Automated Database Concurrency Test (`tests/test_concurrency_postgres.py`)
- **Severity**: Low (Test Suite Fix)
- **Description**: When simulating high-concurrency task claiming under PostgreSQL row locking (`SELECT FOR UPDATE SKIP LOCKED`), test fixture tasks were initialized without the mandatory non-null `assigned_by` field, causing `psycopg2.errors.NotNullViolation`.
- **Resolution**: Updated task creation in `tests/test_concurrency_postgres.py` to supply `assigned_by="system_qa"`.
- **Verification**: Concurrency test passed with 8 concurrent workers racing for 3 tasks, confirming exactly 3 unique claims and 0 double-claims or deadlocks.

---

## 4. Defect: Module-Level Database Mutation Collision in Test Discovery

- **Component**: Automated Test Runner Isolation (`tests/test_security_matrix.py` and `tests/test_concurrency_postgres.py`)
- **Severity**: Medium (Test Harness Integrity)
- **Description**: When running the complete suite under `unittest discover`, module-level imports of `dashboards.common.database` triggered early engine instantiation before isolated test databases could set `POSTGRES_DB`. This caused database collisions with existing test seeds (`duplicate key value violates unique constraint "ix_beds_bed_number"`).
- **Resolution**:
  1. Refactored `tests/test_concurrency_postgres.py` to instantiate its own isolated engine, database, and `SessionLocal` inside `setUp()`.
  2. Refactored `tests/test_security_matrix.py` to use FastAPI's `dependency_overrides[get_db]` bound to its own disposable database inside `setUpClass()`.
  3. Cleaned up dependency overrides and database resources in `tearDownClass()`.
- **Verification**: All 32 tests in the repository now execute and pass concurrently without any database pollution or state leakage (`Ran 32 tests ... OK`).

---

## 5. Defect: Obsolete SQLite References in C++ Build Configuration

- **Component**: C++ Core Engine Build (`CMakeLists.txt`)
- **Severity**: Low (Hygiene / Architecture Consistency)
- **Description**: `CMakeLists.txt` contained legacy comments referencing SQLite. While runtime was PostgreSQL-only, the presence of legacy comments violated the architectural invariant.
- **Resolution**: Removed all obsolete SQLite comments from `CMakeLists.txt`.
- **Verification**: Grep search confirmed zero remaining SQLite references across the entire codebase outside of historical change logs.
