"""Deterministic clinical service checks on disposable PostgreSQL databases."""
import datetime as dt
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboards.common.database import Base
from dashboards.common.models import Alert, HealthCheckSession, Patient, VitalReading
from backend.app.services.alerts import create_vital_alerts
from backend.app.services.patient_analytics import compare_visits, trend_summary
from backend.app.services.patient_attention import assess_patient
from backend.app.services.timeline import patient_timeline
from tests.postgres_support import create_test_database, drop_test_database


class ClinicalServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_name, database_url = create_test_database()
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.patient = Patient(patient_code="TEST-001", full_name="Example Person", blood_group="O+",
                               height_cm=170, weight_kg=70, photo_path="example.jpg")
        self.db.add(self.patient)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        drop_test_database(self.database_name)

    def reading(self, *, temp=None, spo2=None, status="measured", hours_ago=0, session=None):
        row = VitalReading(patient_id=self.patient.id, session_id=session.id if session else None,
                           temperature_c=temp, temperature_status=status if temp is not None else "not_available",
                           pulse_bpm=None, pulse_status="not_available", spo2_percent=spo2,
                           spo2_status=status if spo2 is not None else "not_available",
                           recorded_at=dt.datetime.utcnow() - dt.timedelta(hours=hours_ago), source="ANNA-TEST",
                           quality_status="measured" if status == "measured" else status)
        self.db.add(row)
        self.db.commit()
        return row

    def test_attention_threshold_reasons_and_missing_data(self):
        self.assertEqual(assess_patient(self.db, self.patient)["level"], "OBSERVE")
        self.reading(spo2=90)
        result = assess_patient(self.db, self.patient)
        self.assertEqual(result["level"], "URGENT")
        self.assertTrue(any("SpO2" in reason for reason in result["reasons"]))

    def test_alerts_deduplicate_and_ignore_poor_signal(self):
        first = self.reading(temp=38.4)
        self.assertEqual(len(create_vital_alerts(self.db, first)), 1)
        self.db.commit()
        second = self.reading(temp=38.5)
        self.assertEqual(len(create_vital_alerts(self.db, second)), 0)
        poor = self.reading(spo2=87, status="poor_signal")
        self.assertEqual(len(create_vital_alerts(self.db, poor)), 0)
        self.assertEqual(self.db.query(Alert).count(), 1)

    def test_trends_exclude_unreliable_samples(self):
        self.reading(temp=36.8, hours_ago=2)
        self.reading(temp=37.4, hours_ago=1)
        self.reading(temp=40, status="poor_signal")
        result = trend_summary(self.db, self.patient.id, "6h")["metrics"]["temperature"]
        self.assertEqual(result["sample_count"], 2)
        self.assertAlmostEqual(result["delta"], 0.6)
        self.assertEqual(result["max"], 37.4)

    def test_visit_comparison_and_timeline(self):
        self.assertFalse(compare_visits(self.db, self.patient.id)["previous_available"])
        old = HealthCheckSession(patient_id=self.patient.id, started_at=dt.datetime.utcnow() - dt.timedelta(hours=2),
                                 completed_at=dt.datetime.utcnow() - dt.timedelta(hours=2), status="completed")
        new = HealthCheckSession(patient_id=self.patient.id, started_at=dt.datetime.utcnow() - dt.timedelta(hours=1),
                                 completed_at=dt.datetime.utcnow() - dt.timedelta(hours=1), status="completed")
        self.db.add_all([old, new])
        self.db.commit()
        self.reading(temp=37.0, hours_ago=2, session=old)
        self.reading(temp=38.0, hours_ago=1, session=new)
        result = compare_visits(self.db, self.patient.id)
        self.assertTrue(result["previous_available"])
        self.assertEqual(result["metrics"]["temperature"]["delta"], 1.0)
        timeline = patient_timeline(self.db, self.patient)
        self.assertEqual(timeline, sorted(timeline, key=lambda item: item["timestamp"], reverse=True))


if __name__ == "__main__":
    unittest.main()
