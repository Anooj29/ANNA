"""Realistic SIH 2026 Demonstration Seed Data for a fresh ANNA database.

Seeds:
- 20 beds across Ward A and Ward B
- Staff accounts (passwords supplied through environment variables)
- 12 diverse patients with realistic medical profiles
- Comprehensive historical vitals, emotion logs, wellness answers, medical summaries
- Active and past medications, administration logs
- Clinical alerts with varied severities
- Audit trails
"""

from __future__ import annotations

import datetime as dt
import os
import random
import bcrypt
from sqlalchemy.orm import Session

from dashboards.common.database import SessionLocal, engine
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import inspect
from dashboards.common.models import (
    User,
    Bed,
    Patient,
    RobotTask,
    HealthCheckSession,
    VitalReading,
    PatientResponse,
    EmotionRecord,
    MedicalSummary,
    Medication,
    MedicationLog,
    Alert,
    AuditLog,
)


def hash_secret(secret: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(secret.encode("utf-8"), salt).decode("utf-8")


def seed_database():
    doctor_password = os.environ.get("SEED_DOCTOR_PASSWORD")
    reception_password = os.environ.get("SEED_RECEPTION_PASSWORD")
    patient_pin = os.environ.get("SEED_PATIENT_PIN")
    if not doctor_password or not reception_password or not patient_pin:
        raise RuntimeError("Set SEED_DOCTOR_PASSWORD, SEED_RECEPTION_PASSWORD, and SEED_PATIENT_PIN before seeding.")
    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        raise RuntimeError("Refusing to seed an unversioned existing database. See database/MIGRATIONS.md.")
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    db: Session = SessionLocal()

    try:
        # Check if already seeded
        if any(db.query(model).count() for model in (User, Patient, Bed, RobotTask, VitalReading)):
            raise RuntimeError("Demo seeding requires an empty database; existing records were not changed.")
        random.seed(2026)

        print("Seeding Users...")
        doctor_user = User(
            username="doctor",
            email="doctor@anna.local",
            password_hash=hash_secret(doctor_password),
            role="doctor",
            full_name="Dr. Sarah Rao, MD",
            is_active=True,
            created_at=dt.datetime.utcnow() - dt.timedelta(days=60),
            last_login=dt.datetime.utcnow() - dt.timedelta(hours=2),
        )
        receptionist_user = User(
            username="reception",
            email="reception@anna.local",
            password_hash=hash_secret(reception_password),
            role="receptionist",
            full_name="Priya Sharma",
            is_active=True,
            created_at=dt.datetime.utcnow() - dt.timedelta(days=60),
            last_login=dt.datetime.utcnow() - dt.timedelta(minutes=45),
        )
        db.add_all([doctor_user, receptionist_user])
        db.commit()

        print("Seeding 20 Beds across Ward A & Ward B...")
        beds = []
        for b in range(1, 21):
            ward = "Ward A" if b <= 10 else "Ward B"
            bed_type = "ICU" if b in (1, 11) else ("Step-Down" if b in (2, 12) else "General")
            beds.append(
                Bed(
                    bed_number=b,
                    ward=ward,
                    bed_type=bed_type,
                    is_occupied=False,
                    status="available",
                )
            )
        db.add_all(beds)
        db.commit()

        print("Seeding Patients...")
        patient_profiles = [
            {
                "full_name": "Rohan Verma",
                "dob": "1982-04-12",
                "gender": "Male",
                "blood_group": "B+",
                "height_cm": 174.0,
                "weight_kg": 72.5,
                "phone": "+91 98450 12345",
                "emergency": "+91 98450 67890",
                "address": "42 Indiranagar, Bengaluru",
                "bed_number": 1,
                "days_admitted": 6,
                "discharged": False,
            },
            {
                "full_name": "Ananya Sen",
                "dob": "1994-09-21",
                "gender": "Female",
                "blood_group": "O+",
                "height_cm": 162.0,
                "weight_kg": 56.0,
                "phone": "+91 97110 54321",
                "emergency": "+91 97110 99887",
                "address": "15 Park Street, Kolkata",
                "bed_number": 2,
                "days_admitted": 4,
                "discharged": False,
            },
            {
                "full_name": "David Mitchell",
                "dob": "1968-11-05",
                "gender": "Male",
                "blood_group": "A-",
                "height_cm": 180.0,
                "weight_kg": 84.0,
                "phone": "+91 99001 22334",
                "emergency": "+91 99001 55667",
                "address": "8 Lavelle Road, Bengaluru",
                "bed_number": 3,
                "days_admitted": 7,
                "discharged": False,
            },
            {
                "full_name": "Meera Krishnan",
                "dob": "1976-02-18",
                "gender": "Female",
                "blood_group": "AB+",
                "height_cm": 158.0,
                "weight_kg": 61.2,
                "phone": "+91 94440 33445",
                "emergency": "+91 94440 77889",
                "address": "29 Anna Nagar, Chennai",
                "bed_number": 4,
                "days_admitted": 3,
                "discharged": False,
            },
            {
                "full_name": "Vikram Malhotra",
                "dob": "1990-07-30",
                "gender": "Male",
                "blood_group": "O-",
                "height_cm": 178.0,
                "weight_kg": 76.0,
                "phone": "+91 98200 44556",
                "emergency": "+91 98200 88990",
                "address": "104 Bandra West, Mumbai",
                "bed_number": 5,
                "days_admitted": 2,
                "discharged": False,
            },
            {
                "full_name": "Sunita Patil",
                "dob": "1985-12-14",
                "gender": "Female",
                "blood_group": "A+",
                "height_cm": 165.0,
                "weight_kg": 68.0,
                "phone": "+91 98230 11223",
                "emergency": "+91 98230 44556",
                "address": "7 Kothrud, Pune",
                "bed_number": 11,
                "days_admitted": 5,
                "discharged": False,
            },
            {
                "full_name": "Arjun Nair",
                "dob": "1972-06-08",
                "gender": "Male",
                "blood_group": "B-",
                "height_cm": 172.0,
                "weight_kg": 79.5,
                "phone": "+91 94470 55667",
                "emergency": "+91 94470 99001",
                "address": "12 Panampilly Nagar, Kochi",
                "bed_number": 12,
                "days_admitted": 8,
                "discharged": False,
            },
            {
                "full_name": "Fatima Begum",
                "dob": "1960-03-25",
                "gender": "Female",
                "blood_group": "O+",
                "height_cm": 155.0,
                "weight_kg": 65.0,
                "phone": "+91 98490 66778",
                "emergency": "+91 98490 22334",
                "address": "33 Banjara Hills, Hyderabad",
                "bed_number": 13,
                "days_admitted": 4,
                "discharged": False,
            },
            # Prior discharged patients for historical analytics
            {
                "full_name": "Kavita Reddy",
                "dob": "1988-10-10",
                "gender": "Female",
                "blood_group": "A+",
                "height_cm": 160.0,
                "weight_kg": 54.0,
                "phone": "+91 98480 11223",
                "emergency": "+91 98480 55667",
                "address": "5 Jubilee Hills, Hyderabad",
                "bed_number": None,
                "days_admitted": 14,
                "discharged": True,
            },
            {
                "full_name": "Amitabh Bose",
                "dob": "1965-01-15",
                "gender": "Male",
                "blood_group": "B+",
                "height_cm": 169.0,
                "weight_kg": 74.0,
                "phone": "+91 98300 77889",
                "emergency": "+91 98300 11223",
                "address": "18 Salt Lake, Kolkata",
                "bed_number": None,
                "days_admitted": 12,
                "discharged": True,
            },
        ]

        patient_objs = []
        for i, pdata in enumerate(patient_profiles, start=1):
            code = f"ANP-{i:05d}"
            adm_date = dt.datetime.utcnow() - dt.timedelta(days=pdata["days_admitted"])
            dis_date = (adm_date + dt.timedelta(days=pdata["days_admitted"] - 2)) if pdata["discharged"] else None
            patient = Patient(
                patient_code=code,
                full_name=pdata["full_name"],
                date_of_birth=pdata["dob"],
                gender=pdata["gender"],
                blood_group=pdata["blood_group"],
                height_cm=pdata["height_cm"],
                weight_kg=pdata["weight_kg"],
                phone=pdata["phone"],
                emergency_contact=pdata["emergency"],
                address=pdata["address"],
                photo_path=f"known_faces/{pdata['full_name']}/reference.jpg",
                bed_number=pdata["bed_number"],
                admission_date=adm_date,
                discharge_date=dis_date,
                portal_pin=None,
                portal_pin_hash=hash_secret(patient_pin),
                status="discharged" if pdata["discharged"] else "admitted",
            )
            db.add(patient)
            db.flush()
            patient_objs.append((patient, pdata))

            # If currently in bed, mark bed occupied
            if pdata["bed_number"]:
                bed = db.query(Bed).filter(Bed.bed_number == pdata["bed_number"]).first()
                if bed:
                    bed.is_occupied = True
                    bed.patient_id = patient.id
                    bed.status = "occupied"

        db.commit()

        print("Seeding Health Sessions, Vitals, Emotions, Q&A, and Summaries...")
        emotions_pool = ["Happy", "Neutral", "Neutral", "Sad", "Surprise", "Neutral", "Fear"]
        ecg_notes_pool = [
            "Normal Sinus Rhythm",
            "Normal Sinus Rhythm",
            "Normal Sinus Rhythm",
            "Slightly Irregular",
            "Normal Sinus Rhythm",
        ]

        for patient, pdata in patient_objs:
            # Generate 3-7 historical checkups across admission period
            num_checkups = random.randint(3, 6)
            base_temp = 36.6 if patient.id != 1 else 37.8  # Patient 1 has elevated temperature for alerts demo
            base_pulse = 74 if patient.id != 3 else 96  # Patient 3 has elevated pulse

            for checkup_idx in range(num_checkups):
                days_ago = pdata["days_admitted"] - (checkup_idx * (pdata["days_admitted"] / num_checkups))
                checkup_time = dt.datetime.utcnow() - dt.timedelta(days=days_ago, hours=random.randint(1, 10))

                # Create Task
                task = RobotTask(
                    patient_id=patient.id,
                    assigned_by="Dr. Sarah Rao, MD",
                    task_type="ANNA Health Check",
                    instructions="Standard morning vitals and wellness screening.",
                    priority="urgent" if (patient.id == 1 and checkup_idx == num_checkups - 1) else "normal",
                    status="completed",
                    assigned_at=checkup_time - dt.timedelta(minutes=25),
                    started_at=checkup_time - dt.timedelta(minutes=10),
                    completed_at=checkup_time,
                )
                db.add(task)
                db.flush()

                # Create Session
                session = HealthCheckSession(
                    patient_id=patient.id,
                    robot_task_id=task.id,
                    started_at=checkup_time - dt.timedelta(minutes=10),
                    completed_at=checkup_time,
                    status="completed",
                )
                db.add(session)
                db.flush()

                # Vitals
                # Introduce slight variance
                t_val = round(base_temp + random.uniform(-0.3, 0.4) + (0.2 if checkup_idx == num_checkups - 1 and patient.id == 1 else 0), 1)
                p_val = round(base_pulse + random.randint(-4, 6))
                spo2_val = round(random.uniform(96.0, 99.0) if patient.id != 4 else random.uniform(93.5, 96.0), 1)
                ecg_note = "Slightly Irregular" if (patient.id == 3 and checkup_idx > 2) else random.choice(ecg_notes_pool)

                vital = VitalReading(
                    temperature_status="measured",
                    pulse_status="measured",
                    spo2_status="measured",
                    session_id=session.id,
                    patient_id=patient.id,
                    temperature_c=t_val,
                    pulse_bpm=p_val,
                    spo2_percent=spo2_val,
                    ecg_value="0.92 mV",
                    ecg_note=ecg_note,
                    recorded_at=checkup_time,
                    source="ANNA Robot",
                    quality_status="measured",
                )
                db.add(vital)

                # Emotion
                emo = random.choice(emotions_pool)
                if patient.id == 1 and t_val > 37.8:
                    emo = "Sad"
                emotion_rec = EmotionRecord(
                    session_id=session.id,
                    patient_id=patient.id,
                    emotion=emo,
                    confidence=round(random.uniform(0.88, 0.98), 2),
                    detected_at=checkup_time,
                )
                db.add(emotion_rec)

                # Wellness Q&A
                responses = [
                    ("How many hours of sleep did you get last night?", f"{random.randint(5, 8)} hours"),
                    ("How many glasses of water have you had today?", f"{random.randint(4, 9)} glasses"),
                    ("Are you feeling any pain or discomfort today?", "Mild discomfort" if patient.id == 1 else "No pain"),
                    ("How is your appetite today?", "Normal" if patient.id != 1 else "Reduced"),
                    ("Did you do any physical activity or exercise today?", "Gentle ward walking"),
                    ("On a scale of one to ten, how stressed are you feeling today?", str(random.randint(2, 6))),
                ]
                for q, a in responses:
                    db.add(
                        PatientResponse(
                            session_id=session.id,
                            patient_id=patient.id,
                            question=q,
                            answer=a,
                            created_at=checkup_time,
                        )
                    )

                # Medical Summaries (Dual View)
                clinical_sum = (
                    f"ANNA bedside assessment conducted on {checkup_time.strftime('%Y-%m-%d %H:%M')}. "
                    f"Temperature: {t_val}°C; Pulse: {p_val} BPM (simulated); SpO2: {spo2_val}%; ECG: {ecg_note}. "
                    f"Patient presentation: {emo}. Self-reported sleep was adequate. "
                    f"{'Elevated temperature noted; monitor for infection markers.' if t_val > 37.5 else 'Vitals stable within baseline range.'} "
                    "Requires clinician review; prototype readings are not diagnostic."
                )
                patient_sum = (
                    f"Hello {patient.full_name.split()[0]}! ANNA completed your health check on {checkup_time.strftime('%A, %B %d')}. "
                    f"Your temperature was {t_val}°C, and heart rate was approximately {p_val} BPM. "
                    f"You looked {emo.lower()} during our conversation. "
                    "All your responses have been shared securely with your care team. "
                    "Remember to rest well and stay hydrated!"
                )
                db.add(
                    MedicalSummary(
                        patient_id=patient.id,
                        task_id=task.id,
                        session_id=session.id,
                        author="ANNA Robot",
                        clinical_summary=clinical_sum,
                        patient_summary=patient_sum,
                        temperature_c=f"{t_val} C",
                        pulse_bpm=f"{p_val} BPM",
                        spo2_percent=f"{spo2_val}%",
                        ecg_note=ecg_note,
                        created_at=checkup_time,
                    )
                )

        db.commit()

        print("Seeding Medications and Logs...")
        med_catalog = [
            ("Paracetamol", "650 mg", "Every 8 hours as needed", "08:00, 16:00, 22:00", "Take with water after meals."),
            ("Amoxicillin", "500 mg", "Three times daily", "08:00, 14:00, 20:00", "Complete the full antibiotic course."),
            ("Atorvastatin", "20 mg", "Once daily at bedtime", "21:00", "Take regularly before sleep."),
            ("Metformin", "500 mg", "Twice daily with meals", "08:30, 20:30", "Take with main meals to prevent GI upset."),
            ("Pantoprazole", "40 mg", "Once daily before breakfast", "07:30", "Take on an empty stomach."),
        ]

        for patient, _ in patient_objs[:8]:
            # Assign 2-3 medications per active patient
            for med_info in random.sample(med_catalog, k=random.randint(2, 3)):
                med = Medication(
                    patient_id=patient.id,
                    medicine_name=med_info[0],
                    dosage=med_info[1],
                    frequency=med_info[2],
                    scheduled_time=med_info[3],
                    start_date=patient.admission_date,
                    instructions=med_info[4],
                    status="active",
                )
                db.add(med)
                db.flush()

                # Generate logs
                db.add(
                    MedicationLog(
                        medication_id=med.id,
                        patient_id=patient.id,
                        scheduled_time=dt.datetime.utcnow() - dt.timedelta(hours=4),
                        administered_time=dt.datetime.utcnow() - dt.timedelta(hours=3, minutes=50),
                        status="administered",
                        dispensing_source="Nurse Station - Ward A",
                    )
                )
                db.add(
                    MedicationLog(
                        medication_id=med.id,
                        patient_id=patient.id,
                        scheduled_time=dt.datetime.utcnow() + dt.timedelta(hours=3),
                        administered_time=None,
                        status="pending",
                        dispensing_source="Scheduled",
                    )
                )

        db.commit()

        print("Seeding Alerts and Audit Logs...")
        alerts_data = [
            (
                1,
                "Vital Threshold",
                "URGENT",
                "Elevated core temperature recorded at 38.3°C. Trend analysis indicates continuous upward slope over 36 hours.",
                "active",
            ),
            (
                3,
                "Trend Risk",
                "WARNING",
                "Consecutive slightly irregular ECG observations coupled with elevated resting pulse (101 BPM). Clinician evaluation recommended.",
                "active",
            ),
            (
                4,
                "Vital Threshold",
                "WARNING",
                "SpO2 recorded at 93.8% during afternoon bedside visit. Confirm probe placement or supplemental O2 requirement.",
                "acknowledged",
            ),
            (
                2,
                "High Stress",
                "NORMAL",
                "Self-reported stress level elevated (7/10) with reduced sleep. Patient flagged for supportive nursing interaction.",
                "active",
            ),
        ]
        for p_id, a_type, severity, msg, status in alerts_data:
            alert = Alert(
                patient_id=p_id,
                alert_type=a_type,
                severity=severity,
                message=msg,
                status=status,
                created_at=dt.datetime.utcnow() - dt.timedelta(hours=random.randint(1, 8)),
                acknowledged_at=dt.datetime.utcnow() - dt.timedelta(hours=1) if status == "acknowledged" else None,
                acknowledged_by="Dr. Sarah Rao, MD" if status == "acknowledged" else None,
            )
            db.add(alert)

        # Seed sample Queued tasks for the robot to demonstrate task pickup
        queued_task1 = RobotTask(
            patient_id=1,
            assigned_by="Dr. Sarah Rao, MD",
            task_type="ANNA Health Check",
            instructions="Priority temperature follow-up and symptom inquiry.",
            priority="urgent",
            status="queued",
            assigned_at=dt.datetime.utcnow() - dt.timedelta(minutes=15),
        )
        queued_task2 = RobotTask(
            patient_id=2,
            assigned_by="Dr. Sarah Rao, MD",
            task_type="ANNA Health Check",
            instructions="Routine evening vitals check.",
            priority="normal",
            status="queued",
            assigned_at=dt.datetime.utcnow() - dt.timedelta(minutes=5),
        )
        db.add_all([queued_task1, queued_task2])

        # Audit logs
        audit_entries = [
            ("login", "Doctor Dr. Sarah Rao authenticated via Web Portal", doctor_user.id),
            ("login", "Receptionist Priya Sharma authenticated via Web Portal", receptionist_user.id),
            ("patient_creation", "Admitted patient Rohan Verma (ANP-00001) to Bed 1", receptionist_user.id),
            ("task_assignment", "Assigned urgent ANNA Health Check to Bed 1 (ANP-00001)", doctor_user.id),
            ("health_record_creation", "ANNA Robot completed automated checkup session for ANP-00001", None),
        ]
        for action, details, u_id in audit_entries:
            db.add(
                AuditLog(
                    user_id=u_id,
                    action=action,
                    details=details,
                    timestamp=dt.datetime.utcnow() - dt.timedelta(minutes=random.randint(10, 120)),
                    ip_address="127.0.0.1",
                )
            )

        db.commit()
        print("Database seeded successfully with SIH 2026 demonstration dataset!")

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
