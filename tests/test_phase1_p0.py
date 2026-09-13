"""Isolated smoke/security checks for the initial P0 fixes (stdlib unittest)."""

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

        Base.metadata.create_all(bind=engine)
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


if __name__ == "__main__":
    unittest.main()
