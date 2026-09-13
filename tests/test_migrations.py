"""Migration rehearsal on disposable PostgreSQL with baseline patient data."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text
from tests.postgres_support import create_test_database, drop_test_database

ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_existing_rows_survive_quality_upgrade(self):
        name, url = create_test_database()
        try:
            env = {**os.environ, "DB_ENGINE": "postgres", "POSTGRES_DB": name}
            def alembic(*args):
                result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            alembic("upgrade", "0001")
            stage_engine = create_engine(url)
            try:
                with stage_engine.begin() as conn:
                    conn.execute(text("""INSERT INTO patients
                        (patient_code,full_name,gender,blood_group,height_cm,weight_kg,photo_path,
                         admission_date,status,created_at,updated_at,portal_pin_hash)
                        VALUES ('ANP-LEGACY','Legacy Patient','Unspecified','O+',170,70,'reference.jpg',
                                '2026-01-01','admitted','2026-01-01','2026-01-01','hashed')"""))
                    patient_id = conn.execute(text("SELECT id FROM patients WHERE patient_code='ANP-LEGACY'")).scalar_one()
                    conn.execute(text("""INSERT INTO vital_readings
                        (patient_id,temperature_c,pulse_bpm,spo2_percent,recorded_at,source,quality_status)
                        VALUES (:id,37.1,82,97,'2026-01-01','ANNA Robot','measured')"""), {"id": patient_id})
            finally:
                stage_engine.dispose()
            alembic("upgrade", "head")
            stage_engine = create_engine(url)
            try:
                with stage_engine.connect() as conn:
                    self.assertEqual(conn.execute(text("SELECT full_name FROM patients WHERE id=:id"),
                                                  {"id": patient_id}).scalar_one(), "Legacy Patient")
                    row = conn.execute(text("""SELECT temperature_c,temperature_status,pulse_status,spo2_status
                                              FROM vital_readings WHERE patient_id=:id"""), {"id": patient_id}).one()
                    self.assertEqual(tuple(row), (37.1, "measured", "measured", "measured"))
                    self.assertEqual(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one(), "0005")
            finally:
                stage_engine.dispose()
        finally:
            drop_test_database(name)
