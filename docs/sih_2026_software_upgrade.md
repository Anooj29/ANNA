# SIH 2026 hospital software upgrade progress

The hospital application uses PostgreSQL only. The configured existing
PostgreSQL database was backed up to `~/ANNA-backups`, restored into a
throwaway rehearsal database, migrated, and verified to preserve core table
row counts. It is now at Alembic revision 0005. All ten existing patient
portal PINs have hashes and the plaintext column values are cleared. The
separate `anna_robot/` hardware package has not been changed.

| Part | State | Current implementation or remaining work |
| --- | --- | --- |
| 1 Security hardening | IN PROGRESS | Role gates, persistent login throttle, browser origin checks, PIN cleanup, and protected WebSocket exist; broaden security tests. |
| 2 Alembic foundation | DONE | Baseline and additive migrations; backup/rehearsal helper. |
| 3 Database model | IN PROGRESS | Alerts, notes, tasks, robot status, notifications and typed birth date expanded; more constraints remain. |
| 4 Quality-aware vitals | DONE | Partial and poor readings carry per-metric status, nullable value and provenance. |
| 5 Central backend | DONE | Compatibility dashboard entry points delegate to central app. |
| 6 Response schemas | IN PROGRESS | Reception operational data separated; some clinical routes remain dict-based. |
| 7 Patient attention | DONE | Deterministic levels and reasons in clinician API and workspace. |
| 8 Clinical thresholds | DONE | Environment-configured prototype profile used by attention and alerts. |
| 9 Alert engine | IN PROGRESS | Threshold rules, deduplication, lifecycle and notifications; more trend/quality alerts needed. |
| 10 Patient trends | DONE | Quality-aware stored series and ranges. |
| 11 What changed | DONE | Previous reliable visit comparison and UI. |
| 12 Timeline | IN PROGRESS | Chronological API and patient workspace; pagination needed. |
| 13 Clinical notes | DONE | Role-protected write/read with audit and workspace UI. |
| 14 Audit trail | IN PROGRESS | Important events, admin API and paged admin viewer exist; expand coverage. |
| 15 Robot task backend | IN PROGRESS | Claim, progress, completion and failure contract; concurrency tests needed. |
| 16 Robot status | IN PROGRESS | Heartbeat, clinical status API and fleet panel; hardware integration remains. |
| 17 Realtime events | IN PROGRESS | Authenticated role-filtered WebSocket with event metadata and filtering test; reconnect QA remains. |
| 18 Shared healthcare design | IN PROGRESS | Shared CSS tokens, cards and states; full consistency pass remains. |
| 19 Responsive shell | IN PROGRESS | Chromium checks at 320, 390 and 768px pass across all three signed-in profiles and every staff tab; physical-device and accessibility QA remain. |
| 20 Clinician dashboard | IN PROGRESS | Priority roster and workspace integrated; polish and sorting remain. |
| 21 Patient clinical profile | IN PROGRESS | Workspace profile, note, attention, history; deeper record sections remain. |
| 22 Vital cards | IN PROGRESS | Quality/freshness display exists; full visual pass remains. |
| 23 Vital charts | IN PROGRESS | Range chart exists; interaction and no-data QA remain. |
| 24 What changed UI | DONE | Previous/current values and deltas shown in workspace. |
| 25 Timeline UI | DONE | Chronological events shown in workspace. |
| 26 Alert workspace | IN PROGRESS | Status lifecycle, reason metadata; filters/detail polish remains. |
| 27 Notifications | DONE | Persisted clinician notifications, unread count and read state. |
| 28 Tasks workspace | IN PROGRESS | Queue, stage, robot ID and demo gating; filters remain. |
| 29 Analytics workspace | IN PROGRESS | Clinical aggregates and charts; more cohorts and controls remain. |
| 30 SIH impact analytics | IN PROGRESS | Operations endpoint and clinician panel with explicit estimate formula; benchmark assumptions. |
| 31 Reception dashboard | IN PROGRESS | Shared visual language and assignment workflow; UX QA remains. |
| 32 Bed management | IN PROGRESS | Visual bed grid and reassignment; race/security tests remain. |
| 33 Reception workflow | IN PROGRESS | Intake/doctor/bed/discharge covered; full E2E QA remains. |
| 34 Patient portal | IN PROGRESS | Quality-aware readings and shared style; accessibility/translation remain. |
| 35 Patient trends | IN PROGRESS | Reliable recent series and plain-language comparison; translate dynamic explanations. |
| 36 Reporting | IN PROGRESS | Protected printable patient report and operations CSV; PDF/report tests remain. |
| 37 Medication workflow | IN PROGRESS | Structured schedule migration and prescriber audit; UI and tests remain. |
| 38 AI presentation | IN PROGRESS | Assistive labels, simulation badge, deterministic fallback and source-data action; provenance QA remains. |
| 39 Global search | IN PROGRESS | Role-specific patient searches exist; bed search and keyboard UX remain. |
| 40 Table UX | IN PROGRESS | Server pagination for clinical lists; more sorting and frontend integration remain. |
| 41 Accessibility | IN PROGRESS | Labels, focus states and semantic sections; audit remains. |
| 42 Multilingual readiness | IN PROGRESS | Patient portal interface strings support English, Hindi and Marathi; dynamic messages remain English. |
| 43 Loading/error/empty states | IN PROGRESS | Workspace states added; complete all pages. |
| 44 Health/readiness | DONE | Health and migration-aware readiness endpoints. |
| 45 Structured logging | IN PROGRESS | Structured HTTP events; audit other backend paths. |
| 46 Request IDs | DONE | Request ID propagated in response and log. |
| 47 Pagination | IN PROGRESS | Compatible API envelopes and controls in clinician and reception lists; timeline remains. |
| 48 Performance | IN PROGRESS | Bulk roster attention queries and composite indexes added; benchmark at scale. |
| 49 Cache | DONE | No cache required for current scale; avoids stale clinical data. |
| 50 Automated tests | IN PROGRESS | Isolated PostgreSQL API, service, migration and seed tests; expand coverage. |
| 51 Frontend validation | IN PROGRESS | JavaScript syntax, HTTP smoke and signed-in mobile Chromium layout checks pass; physical-device and full workflow QA remain. |
| 52 CI | IN PROGRESS | PostgreSQL-backed GitHub Actions workflow added; first hosted run pending. |
| 53 Demo seed | IN PROGRESS | Deterministic guarded PostgreSQL demo seed; polish provenance. |
| 54 Demo mode | IN PROGRESS | Simulation feature flag and provenance; full demo pathway remains. |
| 55 Documentation | IN PROGRESS | README and migration guide updated; API guide remains. |
| 56 SIH demo experience | PENDING | Guided walkthrough. |
| 57 Polish | IN PROGRESS | Shared styling and copy; mobile overflow and header overlap fixed, with desktop and device visual QA remaining. |
| 58 Professional copy | IN PROGRESS | Removed embedded credential hints; more copy review remains. |
| 59 Privacy | IN PROGRESS | Role separation and no-store report; retention/log review remains. |
| 60 XSS | IN PROGRESS | Escaping in major dynamic table paths; audit all interpolated HTML. |
| 61 Upload security | IN PROGRESS | Image size/type/dimension/re-encode validation; cleanup tests remain. |
| 62 Dependencies | IN PROGRESS | Dashboard dependencies separated; pin/review versions. |
| 63 Final status | PENDING | Report only after implementation and verification. |

## Verification so far

`python -m unittest discover -s tests -q` passes 20 tests against disposable
PostgreSQL databases. All dashboard JavaScript passes `node --check`; Python
compilation passes. `run.bat` started the central app on port 8000 and the
hub, three role pages, health and readiness endpoints all returned HTTP 200.
The launcher now listens on the local network, prints a Wi-Fi URL, and gives
a clear message if port 8000 is occupied. Signed-in Chromium checks at 320,
390 and 768 CSS pixels covered all clinician and reception tabs plus the
patient portal; no page-wide horizontal overflow remained after the mobile
CSS changes. Phone screenshots were visually inspected at 390px. LAN access
from a physical phone still depends on the Windows network/firewall setup.
The physical robot integration and real hospital deployment require their
external equipment and credentials; the authenticated API adapter is present.
