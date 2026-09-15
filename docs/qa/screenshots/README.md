# ANNA Visual Screenshot QA Catalog (SIH 2026)

This directory contains automated, high-resolution browser verification screenshots captured across all three primary user profiles, multiple device viewports, and edge/error states using Playwright Chromium (`chrome` channel) connected to the live PostgreSQL 18.6 hospital server.

---

## 1. Receptionist Profile (`/receptionist`)

| Screenshot | Description | Viewport |
| :--- | :--- | :--- |
| `01_login.png` | Initial Receptionist sign-in overlay card with credentials prompt. | 1440 × 900 Desktop |
| `02_reception_overview.png` | Main Ward Bed Allocation Map and top KPI cards (Total Beds, Occupied, Available, Admissions). | 1440 × 900 Desktop |
| `03_reception_beds.png` | Interactive Ward Bed Map (Ward A & Ward B bed status cards). | 1440 × 900 Desktop |
| `04_reception_admit.png` | Patient Admission & Face Enrollment Form (demographics, bed assignment, photo intake). | 1440 × 900 Desktop |
| `05_reception_directory.png` | Patient Directory tab with search filter, active inpatients table, and quick actions. | 1440 × 900 Desktop |
| `06_reception_analytics.png` | Reception & Ward Capacity Analytics rendered with the offline charting engine (occupancy donut, ward comparison, turnover volume). | 1440 × 900 Desktop |

---

## 2. Clinician Profile (`/clinician`)

| Screenshot | Description | Viewport |
| :--- | :--- | :--- |
| `10_clinician_overview.png` | Clinical Command center with KPIs, Attention Roster, and inpatient status roster table. | 1440 × 900 Desktop |
| `11_clinician_priority_roster.png` | Prioritized patient attention list ranked deterministically by vitals heuristics and risk flags. | 1440 × 900 Desktop |
| `12_clinician_patient_profile.png` | Comprehensive Patient Workspace showing demographics, assigned bed, and attention level. | 1440 × 900 Desktop |
| `13_clinician_vitals.png` | Patient Workspace physiological vitals cards (Temperature, Pulse, SpO2, ECG rhythm). | 1440 × 900 Desktop |
| `14_clinician_trends.png` | Patient Workspace vital trends canvas with 6h/24h/7d/30d historical ranges. | 1440 × 900 Desktop |
| `15_clinician_timeline.png` | Longitudinal patient clinical timeline displaying rounds, alerts, and visit notes chronologically. | 1440 × 900 Desktop |
| `16_clinician_alerts.png` | Alert Center tab displaying physiological threshold triggers, severity badges, and doctor sign-off buttons. | 1440 × 900 Desktop |
| `17_clinician_tasks.png` | ANNA Task Queue tab showing queued, in-progress, and completed autonomous robot visits. | 1440 × 900 Desktop |
| `18_clinician_analytics.png` | Clinical Analytics tab showing population risk stratification, fleet tasks, and 7-day visit volume. | 1440 × 900 Desktop |
| `19_clinician_reports.png` | Dual Medical Reports tab comparing formal clinical observations with plain-language patient summaries. | 1440 × 900 Desktop |

---

## 3. Patient Care Portal (`/patient`)

| Screenshot | Description | Viewport |
| :--- | :--- | :--- |
| `20_patient_home_en.png` | Patient Care Portal home view (English) with warm greeting, bed tag, and latest readings cards. | 1440 × 900 Desktop |
| `21_patient_trends_en.png` | Patient visual health progress chart with reassuring trend summaries. | 1440 × 900 Desktop |
| `22_patient_medications_en.png` | Patient prescribed medication guide with dosage, frequency, schedule, and nurse instructions. | 1440 × 900 Desktop |
| `23_patient_hindi.png` | Multilingual localization in Hindi (हिन्दी) across navigation, cards, and medical disclaimers. | 1440 × 900 Desktop |
| `24_patient_marathi.png` | Multilingual localization in Marathi (मराठी) across navigation, cards, and medical disclaimers. | 1440 × 900 Desktop |
| `25_patient_reports.png` | Patient visit conversation history stream with friendly, plain-language checkup summaries. | 1440 × 900 Desktop |

---

## 4. Responsive Viewport Adaptations

| Screenshot | Description | Viewport |
| :--- | :--- | :--- |
| `30_mobile_reception.png` | Receptionist dashboard responsive mobile layout with stacked KPI grid and collapsible bed map. | 390 × 844 Mobile |
| `31_mobile_clinician.png` | Clinician dashboard mobile layout with responsive tables, touch-friendly buttons, and horizontal overflow prevention. | 390 × 844 Mobile |
| `32_mobile_patient.png` | Patient portal mobile layout with fixed bottom navigation bar (Home, Health, Meds, History). | 390 × 844 Mobile |
| `33_tablet_clinician.png` | Clinician command center on tablet viewport with optimized split cards and roster. | 768 × 1024 Tablet |
| `34_mobile_narrow_patient.png` | Patient portal on ultra-narrow compact screen with full text readability and no horizontal overflow. | 320 × 640 Compact |

---

## 5. Error, Empty, and Edge States

| Screenshot | Description | Viewport |
| :--- | :--- | :--- |
| `40_error_state.png` | Authentication failure state displaying user-friendly, non-technical error alerts. | 1440 × 900 Desktop |
| `41_empty_state.png` | Empty workspace guidance state when no patient is selected. | 1440 × 900 Desktop |
| `42_offline_state.png` | Robot fleet queue indicating task execution status and idle/offline states. | 1440 × 900 Desktop |
