"""PostgreSQL 18.6 Concurrency and Row-Level Locking Verification Suite for ANNA.

Validates that:
1. Simultaneous robot workers claiming tasks via SELECT FOR UPDATE SKIP LOCKED never double-claim or deadlock.
2. Concurrent bed assignment attempts for the same bed result in exactly one winner and conflicts for the rest.
"""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.postgres_support import create_test_database, drop_test_database


class TestPostgresConcurrency(unittest.TestCase):
    def setUp(self):
        from dashboards.common.database import Base
        from dashboards.common.models import Bed, Patient, RobotTask

        self.Bed = Bed
        self.Patient = Patient
        self.RobotTask = RobotTask

        self.db_name, db_url = create_test_database()
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        with self.SessionLocal() as db:
            self.patient = Patient(
                patient_code="CONC-001",
                full_name="Concurrency Patient",
                blood_group="O+",
                height_cm=170,
                weight_kg=70,
                photo_path="conc.jpg",
                status="admitted",
            )
            db.add(self.patient)
            db.commit()
            db.refresh(self.patient)
            self.patient_id = self.patient.id

    def tearDown(self):
        self.engine.dispose()
        drop_test_database(self.db_name)

    def test_01_concurrent_task_claiming_skip_locked(self):
        """Verify SELECT FOR UPDATE SKIP LOCKED prevents double-claiming under high concurrency."""
        with self.SessionLocal() as db:
            tasks = []
            for i in range(3):
                t = self.RobotTask(
                    patient_id=self.patient_id,
                    assigned_by="system_qa",
                    task_type="vitals_check",
                    priority="routine",
                    status="queued",
                    instructions=f"Concurrency verification task {i}",
                )
                db.add(t)
                tasks.append(t)
            db.commit()
            task_ids = [t.id for t in tasks]

        claimed_task_ids = []
        lock = threading.Lock()

        def claim_worker(worker_id):
            with self.SessionLocal() as worker_db:
                task = (
                    worker_db.query(self.RobotTask)
                    .filter(self.RobotTask.id.in_(task_ids), self.RobotTask.status == "queued")
                    .with_for_update(skip_locked=True)
                    .first()
                )
                if task:
                    task.status = "in_progress"
                    task.robot_id = f"ANNA-ROBOT-{worker_id}"
                    worker_db.commit()
                    with lock:
                        claimed_task_ids.append((worker_id, task.id))
                    return task.id
                return None

        # Run 8 concurrent workers racing for 3 tasks
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(claim_worker, range(8)))

        successful_claims = [r for r in results if r is not None]
        self.assertEqual(len(successful_claims), 3, "Exactly 3 tasks should be claimed")
        self.assertEqual(len(set(successful_claims)), 3, "All claimed tasks must be unique (no double claims)")

    def test_02_concurrent_bed_assignment_lock(self):
        """Verify row-level locking on Bed prevents conflicting admissions."""
        with self.SessionLocal() as db:
            test_bed = self.Bed(bed_number=101, ward="Ward A", is_occupied=False)
            db.add(test_bed)
            db.commit()
            target_bed_num = test_bed.bed_number

        def admission_worker(worker_id):
            with self.SessionLocal() as worker_db:
                try:
                    bed = worker_db.query(self.Bed).filter(self.Bed.bed_number == target_bed_num).with_for_update().first()
                    if not bed:
                        return "not_found"
                    if bed.is_occupied:
                        return "conflict"

                    occ = worker_db.query(self.Patient).filter(self.Patient.bed_number == target_bed_num, self.Patient.status == "admitted").first()
                    if occ:
                        return "conflict"

                    bed.is_occupied = True
                    worker_db.commit()
                    return "success"
                except Exception as e:
                    worker_db.rollback()
                    return f"error: {e}"

        # Run 4 concurrent workers attempting to allocate the same bed
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(admission_worker, range(4)))

        success_count = results.count("success")
        conflict_count = results.count("conflict")

        self.assertEqual(success_count, 1, f"Expected exactly 1 successful bed allocation, got {results}")
        self.assertEqual(conflict_count, 3, f"Expected 3 conflicts, got {results}")


if __name__ == "__main__":
    unittest.main()
