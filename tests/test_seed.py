"""Demo seed runs only on a fresh migrated PostgreSQL database."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text
from tests.postgres_support import create_test_database, drop_test_database

ROOT = Path(__file__).resolve().parents[1]


class DemoSeedTests(unittest.TestCase):
    def test_seed_fresh_database_and_refuse_repeat(self):
        name, url = create_test_database()
        try:
            env = {**os.environ, "DB_ENGINE": "postgres", "POSTGRES_DB": name,
                   "SEED_DOCTOR_PASSWORD": "random-test-password", "SEED_RECEPTION_PASSWORD": "another-test-password",
                   "SEED_PATIENT_PIN": "123987"}
            first = subprocess.run([sys.executable, "-m", "database.seed_data"], cwd=ROOT, env=env,
                                   text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            stage_engine = create_engine(url)
            try:
                with stage_engine.connect() as conn:
                    before = conn.execute(text("SELECT COUNT(*) FROM patients")).scalar_one()
                    self.assertGreaterEqual(before, 10)
                    self.assertEqual(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one(), "0006")
            finally:
                stage_engine.dispose()
            again = subprocess.run([sys.executable, "-m", "database.seed_data"], cwd=ROOT, env=env,
                                   text=True, capture_output=True)
            self.assertNotEqual(again.returncode, 0)
            stage_engine = create_engine(url)
            try:
                with stage_engine.connect() as conn:
                    self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM patients")).scalar_one(), before)
            finally:
                stage_engine.dispose()
        finally:
            drop_test_database(name)
