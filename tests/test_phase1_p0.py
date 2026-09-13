import datetime as dt
import os
import unittest

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

# Module imports during discovery can initialize shared configuration before
# setUpClass. Pin this suite to disposable PostgreSQL before app imports.
from tests.postgres_support import create_test_database, drop_test_database
_test_database_name, _ = create_test_database()
os.environ["DB_ENGINE"] = "postgres"
os.environ["POSTGRES_DB"] = _test_database_name
os.environ["DASHBOARD_SESSION_SECRET"] = "test-only-session-secret-with-enough-length"
os.environ["ROBOT_API_KEY"] = "test-only-robot-key"


class Phase1P0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):

        from backend.app.main import app
        from dashboards.common.database import Base, SessionLocal, engine
        from dashboards.common.models import Bed, Patient, RobotTask, User
        from backend.app.auth import hash_password
        from sqlalchemy import text as sql_text

        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(sql_text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            conn.execute(sql_text("INSERT INTO alembic_version (version_num) VALUES ('0006') ON CONFLICT DO NOTHING"))
        with SessionLocal.begin() as db:
            db.add_all([
                User(username="doctor", email="doctor@test.local", password_hash=hash_password("doctor-pass"), role="doctor", full_name="Test Doctor"),
                User(username="nurse", email="nurse@test.local", password_hash=hash_password("nurse-pass"), role="nurse", full_name="Test Nurse"),
                User(username="admin", email="admin@test.local", password_hash=hash_password("admin-pass"), role="admin", full_name="Test Admin"),
                User(username="reception", email="reception@test.local", password_hash=hash_password("reception-pass"), role="receptionist", full_name="Test Reception"),
                Bed(bed_number=1, ward="Ward A"),
                Patient(patient_code="ANP-00001", full_name="Test Patient", blood_group="O+", height_cm=170, weight_kg=70, photo_path="test.jpg", bed_number=1, portal_pin_hash=hash_password("123999")),
            ])
        with SessionLocal.begin() as db:
            patient = db.query(Patient).first()
            db.add(RobotTask(patient_id=patient.id, assigned_by="Test Doctor", status="in_progress"))

        cls.app = app
        cls.SessionLocal = SessionLocal

    @classmethod
    def tearDownClass(cls):
        from dashboards.common.database import engine
        engine.dispose()
        drop_test_database(_test_database_name)

    def test_admission_route_exists_and_is_protected(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.post("/api/patients").status_code, 401)
            self.assertNotEqual(client.post("/api/patients/admit").status_code, 200)

    def test_role_restrictions_and_reception_directory(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/patients").status_code, 401)
            self.assertEqual(client.get("/api/beds").status_code, 401)
            client.post("/api/auth/login", json={"username_or_email": "reception", "password": "reception-pass"})
            self.assertEqual(client.get("/api/patients").status_code, 403)
            response = client.get("/api/receptionist/patients")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("portal_pin", response.text)
            self.assertNotIn("height_cm", response.text)

    def test_websocket_requires_staff_session(self):
        with TestClient(self.app) as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("/ws/hospital"):
                    pass

    def test_cross_site_mutation_rejected(self):
        with TestClient(self.app) as client:
            response = client.post("/api/auth/login", headers={"Origin": "https://attacker.example"},
                                   json={"username_or_email": "doctor", "password": "doctor-pass"})
            self.assertEqual(response.status_code, 403)

    def test_persistent_login_throttle(self):
        with TestClient(self.app) as client:
            for _ in range(5):
                response = client.post("/api/auth/login", json={"username_or_email": "unknown-throttle-test",
                                                                    "password": "incorrect"})
                self.assertEqual(response.status_code, 401)
            blocked = client.post("/api/auth/login", json={"username_or_email": "unknown-throttle-test",
                                                             "password": "incorrect"})
            self.assertEqual(blocked.status_code, 429)

    def test_robot_heartbeat_progress_and_clinical_status(self):
        from dashboards.common.models import RobotTask
        with self.SessionLocal.begin() as db:
            task = RobotTask(patient_id=1, assigned_by="Test Doctor", status="in_progress", robot_id="ANNA-TEST")
            db.add(task)
            db.flush()
            task_id = task.id
        with TestClient(self.app) as client:
            headers = {"X-Anna-Robot-Key": "test-only-robot-key"}
            heartbeat = client.post("/api/robot/heartbeat", headers=headers,
                                    json={"robot_id": "ANNA-TEST", "status": "busy", "current_task_id": task_id})
            self.assertEqual(heartbeat.status_code, 200, heartbeat.text)
            progress = client.post(f"/api/robot/tasks/{task_id}/progress", headers=headers,
                                   json={"robot_id": "ANNA-TEST", "stage": "vitals"})
            self.assertEqual(progress.status_code, 200, progress.text)
            self.assertEqual(client.get("/api/robot/status").status_code, 401)
            client.post("/api/auth/login", json={"username_or_email": "doctor", "password": "doctor-pass"})
            status = client.get("/api/robot/status")
            self.assertEqual(status.status_code, 200)
            self.assertTrue(any(row["robot_id"] == "ANNA-TEST" for row in status.json()))

    def test_medication_schedule_and_alert_lifecycle(self):
        from dashboards.common.models import Alert, Medication
        with self.SessionLocal.begin() as db:
            alert = Alert(patient_id=1, alert_type="Vital Threshold", severity="WARNING",
                          message="Test alert", status="new")
            db.add(alert)
            db.flush()
            alert_id = alert.id
        with TestClient(self.app) as client:
            client.post("/api/auth/login", json={"username_or_email": "doctor", "password": "doctor-pass"})
            prescription = client.post("/api/patients/ANP-00001/medications",
                                       json={"medicine_name": "Test medicine", "dosage": "1 tablet",
                                             "frequency": "Twice daily", "schedule_times": ["08:00", "20:00"]})
            self.assertEqual(prescription.status_code, 200, prescription.text)
            medication_id = prescription.json()["medication_id"]
            with self.SessionLocal() as db:
                self.assertEqual(db.get(Medication, medication_id).schedule_times, ["08:00", "20:00"])
            self.assertEqual(client.patch(f"/api/alerts/{alert_id}/status", json={"status": "under_review"}).status_code, 200)
            self.assertEqual(client.patch(f"/api/alerts/{alert_id}/status", json={"status": "resolved", "note": "Reviewed"}).status_code, 200)
            self.assertEqual(client.post(f"/api/patients/ANP-00001/medications/{medication_id}/discontinue").status_code, 200)

    def test_nurse_and_admin_least_privilege(self):
        with TestClient(self.app) as client:
            client.post("/api/auth/login", json={"username_or_email": "nurse", "password": "nurse-pass"})
            self.assertEqual(client.get("/api/clinician/priority").status_code, 200)
            self.assertEqual(client.get("/api/admin/audit").status_code, 403)
            self.assertEqual(client.post("/api/patients/ANP-00001/portal-pin").status_code, 403)
            self.assertEqual(client.post("/api/patients/ANP-00001/medications",
                                         json={"medicine_name": "Test", "dosage": "1", "frequency": "daily",
                                               "schedule_times": ["09:00"]}).status_code, 403)
            client.post("/api/auth/login", json={"username_or_email": "admin", "password": "admin-pass"})
            self.assertEqual(client.get("/api/admin/audit").status_code, 200)

    def test_notifications_are_clinical_and_user_scoped(self):
        from dashboards.common.models import RobotTask
        with self.SessionLocal.begin() as db:
            task = RobotTask(patient_id=1, assigned_by="Test Doctor", status="in_progress")
            db.add(task)
            db.flush()
            task_id = task.id
        with TestClient(self.app) as client:
            robot = client.post(f"/api/robot/tasks/{task_id}/complete",
                                headers={"X-Anna-Robot-Key": "test-only-robot-key"},
                                json={"status": "completed", "temperature_c": "39.4 C"})
            self.assertEqual(robot.status_code, 200)
            self.assertEqual(client.get("/api/clinician/notifications").status_code, 401)
            client.post("/api/auth/login", json={"username_or_email": "reception", "password": "reception-pass"})
            self.assertEqual(client.get("/api/clinician/notifications").status_code, 403)
            client.post("/api/auth/login", json={"username_or_email": "doctor", "password": "doctor-pass"})
            result = client.get("/api/clinician/notifications")
            self.assertEqual(result.status_code, 200)
            items = result.json()["items"]
            self.assertTrue(any(item["event_type"] == "alert" for item in items))
            self.assertEqual(client.post(f"/api/clinician/notifications/{items[0]['id']}/read").status_code, 200)

    def test_pagination_and_printable_report_require_clinical_role(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/reports/patients/ANP-00001").status_code, 401)
            client.post("/api/auth/login", json={"username_or_email": "doctor", "password": "doctor-pass"})
            for path in ("/api/patients?active_only=true", "/api/tasks", "/api/alerts?status=all"):
                separator = "&" if "?" in path else "?"
                result = client.get(path + separator + "page=1&page_size=1")
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()["page_size"], 1)
                self.assertIn("items", result.json())
            report = client.get("/api/reports/patients/ANP-00001")
            self.assertEqual(report.status_code, 200)
            self.assertIn("Test Patient", report.text)
            self.assertEqual(report.headers["cache-control"], "no-store")
            self.assertEqual(client.get("/api/reports/operations.csv").status_code, 200)
            self.assertEqual(client.get("/api/clinician/patient-options").status_code, 200)
        with TestClient(self.app) as client:
            client.post("/api/auth/login", json={"username_or_email": "reception", "password": "reception-pass"})
            directory = client.get("/api/receptionist/patients?page=1&page_size=1&status=admitted")
            self.assertEqual(directory.status_code, 200)
            self.assertEqual(directory.json()["page_size"], 1)

    def test_patient_portal_is_isolated_and_hash_only(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/portal/profile").status_code, 401)
            login = client.post("/api/portal/auth/login", json={"patient_code": "ANP-00001", "portal_pin": "123999"})
            self.assertEqual(login.status_code, 200)
            self.assertEqual(client.get("/api/portal/profile").json()["patient_code"], "ANP-00001")
            self.assertEqual(client.get("/api/patients").status_code, 401)

    def test_compatibility_port_uses_central_security(self):
        from dashboards.receptionist.main import app as reception_app
        with TestClient(reception_app) as client:
            self.assertEqual(client.get("/", follow_redirects=False).status_code, 307)
            self.assertEqual(client.get("/api/beds").status_code, 401)
            self.assertEqual(client.get("/receptionist/static/app.js").status_code, 200)

    def test_invalid_completion_and_failed_task_do_not_fabricate_vitals(self):
        with TestClient(self.app) as client:
            headers = {"X-Anna-Robot-Key": "test-only-robot-key"}
            invalid = client.post("/api/robot/tasks/1/complete", headers=headers, json={"status": "completed", "temperature_c": "bad", "pulse_bpm": "75 BPM", "spo2_percent": "98%"})
            self.assertEqual(invalid.status_code, 200)
            from dashboards.common.models import RobotTask, VitalReading
            with self.SessionLocal.begin() as db:
                self.assertEqual(db.get(RobotTask, 1).status, "completed")
                reading = db.query(VitalReading).first()
                self.assertIsNone(reading.temperature_c)
                self.assertEqual(reading.temperature_status, "invalid")
                db.add(RobotTask(patient_id=1, assigned_by="Test Doctor", status="in_progress"))
            failed = client.post("/api/robot/tasks/2/complete", headers=headers, json={"status": "failed", "failure_reason": "sensor offline"})
            self.assertEqual(failed.status_code, 200)
            with self.SessionLocal() as db:
                self.assertEqual(db.get(RobotTask, 2).status, "failed")
                self.assertEqual(db.query(VitalReading).count(), 1)

    def test_health_and_ready_endpoints(self):
        with TestClient(self.app) as client:
            res_health = client.get("/api/health")
            self.assertEqual(res_health.status_code, 200)
            self.assertEqual(res_health.json()["backend"], "ok")

            res_ready = client.get("/api/ready")
            self.assertEqual(res_ready.status_code, 200)
            self.assertEqual(res_ready.json()["revision"], "0006")

            res_cap = client.get("/api/capabilities")
            self.assertEqual(res_cap.status_code, 200)

    def test_timeline_pagination_and_event_filtering(self):
        with TestClient(self.app) as client:
            client.post("/api/auth/login", json={"username_or_email": "doctor", "password": "doctor-pass"})
            res = client.get("/api/patients/ANP-00001/timeline?page=1&page_size=2")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("items", data)
            self.assertIn("total", data)
            self.assertEqual(data["page"], 1)
            self.assertEqual(data["page_size"], 2)
            self.assertLessEqual(len(data["items"]), 2)

            res_filter = client.get("/api/patients/ANP-00001/timeline?event_type=ADMISSION")
            self.assertEqual(res_filter.status_code, 200)
            filtered = res_filter.json()
            self.assertTrue(all("ADMISSION" in item["event_type"] for item in filtered["items"]))

    def test_alert_lifecycle_expanded(self):
        from dashboards.common.models import Alert
        with self.SessionLocal.begin() as db:
            alert = Alert(patient_id=1, alert_type="Vital Threshold", severity="URGENT",
                          message="Urgent temperature breach", status="active")
            db.add(alert)
            db.flush()
            alert_id = alert.id

        with TestClient(self.app) as client:
            # Nurse can move to under_review
            client.post("/api/auth/login", json={"username_or_email": "nurse", "password": "nurse-pass"})
            res_review = client.patch(f"/api/alerts/{alert_id}/status", json={"status": "under_review", "note": "Observing"})
            self.assertEqual(res_review.status_code, 200)

            # Nurse cannot dismiss (requires doctor/admin)
            res_nurse_dismiss = client.patch(f"/api/alerts/{alert_id}/status", json={"status": "dismissed", "note": "Dismissed"})
            self.assertEqual(res_nurse_dismiss.status_code, 403)

            # Doctor can dismiss with note
            client.post("/api/auth/login", json={"username_or_email": "doctor", "password": "doctor-pass"})
            res_doc_dismiss = client.patch(f"/api/alerts/{alert_id}/status", json={"status": "dismissed", "note": "Doctor dismissed"})
            self.assertEqual(res_doc_dismiss.status_code, 200)
            self.assertEqual(res_doc_dismiss.json()["status"], "dismissed")

            # Closed alert cannot transition again
            res_reclose = client.patch(f"/api/alerts/{alert_id}/status", json={"status": "resolved", "note": "Try re-resolve"})
            self.assertEqual(res_reclose.status_code, 409)

    def test_patient_reports_and_audit_export(self):
        with TestClient(self.app) as client:
            client.post("/api/auth/login", json={"username_or_email": "doctor", "password": "doctor-pass"})
            
            # HTML clinical report
            report_res = client.get("/api/reports/patients/ANP-00001?days=7")
            self.assertEqual(report_res.status_code, 200)
            self.assertIn("Test Patient", report_res.text)
            self.assertIn("ANNA clinical visit report", report_res.text)
            self.assertEqual(report_res.headers.get("Cache-Control"), "no-store")

            # CSV operations export
            csv_res = client.get("/api/reports/operations.csv?days=7")
            self.assertEqual(csv_res.status_code, 200)
            self.assertIn("text/csv", csv_res.headers.get("content-type"))
            self.assertIn("Metric,Value", csv_res.text)

            # Admin audit log check
            client.post("/api/auth/login", json={"username_or_email": "admin", "password": "admin-pass"})
            audit_res = client.get("/api/admin/audit?limit=20")
            self.assertEqual(audit_res.status_code, 200)
            actions = [item["action"] for item in audit_res.json()["items"]]
            self.assertIn("patient_report_viewed", actions)
            self.assertIn("operations_csv_exported", actions)

    def test_robot_task_claim_priority_and_heartbeat(self):
        from dashboards.common.models import RobotTask
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        with self.SessionLocal.begin() as db:
            t_normal = RobotTask(patient_id=1, assigned_by="Test Doctor", status="queued", priority="normal", assigned_at=now - dt.timedelta(minutes=10))
            t_urgent = RobotTask(patient_id=1, assigned_by="Test Doctor", status="queued", priority="urgent", assigned_at=now - dt.timedelta(minutes=5))
            db.add_all([t_normal, t_urgent])

        with TestClient(self.app) as client:
            headers = {"X-Anna-Robot-Key": "test-only-robot-key"}
            claim_res = client.post("/api/robot/tasks/next", headers=headers, json={"robot_id": "ANNA-ROBOT-01"})
            self.assertEqual(claim_res.status_code, 200)
            # Urgent task must be prioritized over earlier normal task
            self.assertEqual(claim_res.json()["priority"], "urgent")

            # Heartbeat update
            hb_res = client.post("/api/robot/heartbeat", headers=headers, json={
                "robot_id": "ANNA-ROBOT-01",
                "status": "online",
                "battery_percent": 95.0,
                "current_task_id": claim_res.json()["id"]
            })
            self.assertEqual(hb_res.status_code, 200)

            # Clinician views robot status
            client.post("/api/auth/login", json={"username_or_email": "doctor", "password": "doctor-pass"})
            status_res = client.get("/api/robot/status")
            self.assertEqual(status_res.status_code, 200)
            self.assertTrue(any(r["robot_id"] == "ANNA-ROBOT-01" for r in status_res.json()))


if __name__ == "__main__":
    unittest.main()

