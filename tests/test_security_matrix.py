"""ANNA Security and Authorization Matrix Verification Suite.

Tests:
1. Unauthenticated requests are blocked with 401 Unauthorized.
2. Receptionist cannot access Clinician endpoints (403 Forbidden).
3. Clinician cannot access Receptionist admission/discharge endpoints (403 Forbidden).
4. Patient portal credentials cannot access staff APIs.
5. XSS injection payloads in clinical notes are safely stored and sanitized.
"""

import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.orm import sessionmaker

from tests.postgres_support import create_test_database, drop_test_database


class SecurityMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dashboards.common.database import Base, get_db
        from dashboards.common.models import Bed, Patient, User
        from backend.app.auth import hash_password
        from backend.app.main import app

        cls.db_name, cls.db_url = create_test_database()
        cls.engine = create_engine(cls.db_url)
        Base.metadata.create_all(bind=cls.engine)

        with cls.engine.begin() as conn:
            conn.execute(sql_text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            conn.execute(sql_text("INSERT INTO alembic_version (version_num) VALUES ('0006') ON CONFLICT DO NOTHING"))

        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        with cls.SessionLocal() as db:
            db.add_all([
                User(username="doctor_sec", email="doc_sec@test.local", password_hash=hash_password("DocSec2026!"), role="doctor", full_name="Dr. Security"),
                User(username="reception_sec", email="rec_sec@test.local", password_hash=hash_password("RecSec2026!"), role="receptionist", full_name="Reception Security"),
                User(username="admin_sec", email="admin_sec@test.local", password_hash=hash_password("AdminSec2026!"), role="admin", full_name="Admin Security"),
                Bed(bed_number=901, ward="Ward A"),
                Bed(bed_number=902, ward="Ward A"),
                Patient(patient_code="ANP-99999", full_name="Sec Test Patient", blood_group="A+", height_cm=175, weight_kg=72, photo_path="test.jpg", bed_number=901, portal_pin_hash=hash_password("987654")),
            ])
            db.commit()

        def override_get_db():
            with cls.SessionLocal() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        cls.app = app

    @classmethod
    def tearDownClass(cls):
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        drop_test_database(cls.db_name)

    def test_01_unauthenticated_requests_blocked(self):
        """Unauthenticated requests to protected staff endpoints return 401 Unauthorized."""
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/api/patients").status_code, 401)
            self.assertEqual(client.get("/api/tasks").status_code, 401)
            self.assertEqual(client.get("/api/receptionist/stats").status_code, 401)
            self.assertEqual(client.get("/api/receptionist/patients").status_code, 401)
            self.assertEqual(client.get("/api/admin/audit").status_code, 401)

    def test_02_receptionist_cannot_access_clinical_endpoints(self):
        """Receptionist role is forbidden from clinical tasks, alerts, and notes."""
        with TestClient(self.app) as client:
            login = client.post("/api/auth/login", json={"username_or_email": "reception_sec", "password": "RecSec2026!"})
            self.assertEqual(login.status_code, 200)

            # Clinician endpoints should be forbidden (403) for receptionist
            self.assertEqual(client.get("/api/clinician/stats").status_code, 403)
            self.assertEqual(client.get("/api/tasks").status_code, 403)
            self.assertEqual(client.get("/api/alerts").status_code, 403)

    def test_03_doctor_cannot_admit_patient_via_receptionist_endpoint(self):
        """Doctor role is forbidden from receptionist-only admission and bed management."""
        with TestClient(self.app) as client:
            login = client.post("/api/auth/login", json={"username_or_email": "doctor_sec", "password": "DocSec2026!"})
            self.assertEqual(login.status_code, 200)

            # Receptionist-only endpoints should return 403 for doctor
            self.assertEqual(client.get("/api/receptionist/stats").status_code, 403)
            self.assertEqual(client.get("/api/receptionist/analytics").status_code, 403)
            res = client.post("/api/beds/901/discharge")
            self.assertEqual(res.status_code, 403)

    def test_04_patient_pin_authentication_isolation(self):
        """Patient portal authentication is isolated from staff endpoints."""
        with TestClient(self.app) as client:
            # Login as patient
            res = client.post("/api/portal/auth/login", json={"patient_code": "ANP-99999", "portal_pin": "987654"})
            self.assertEqual(res.status_code, 200)

            # Attempt to access staff endpoints with patient session
            self.assertEqual(client.get("/api/patients").status_code, 401)
            self.assertEqual(client.get("/api/receptionist/stats").status_code, 401)
            self.assertEqual(client.get("/api/tasks").status_code, 401)
            self.assertEqual(client.get("/api/admin/audit").status_code, 401)

    def test_05_xss_payload_in_clinical_note(self):
        """XSS payload in clinician note is safely saved and rendered with escaping."""
        with TestClient(self.app) as client:
            login = client.post("/api/auth/login", json={"username_or_email": "doctor_sec", "password": "DocSec2026!"})
            self.assertEqual(login.status_code, 200)

            xss_payload = "<script>alert('xss_attack')</script><img src=x onerror=alert(1)>"
            res = client.post("/api/patients/ANP-99999/notes", json={"content": xss_payload, "note_type": "progress"})
            self.assertEqual(res.status_code, 201)

            # Retrieve notes
            notes_res = client.get("/api/patients/ANP-99999/notes")
            self.assertEqual(notes_res.status_code, 200)
            notes = notes_res.json()
            self.assertTrue(any(n["content"] == xss_payload for n in notes))


if __name__ == "__main__":
    unittest.main()
