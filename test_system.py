"""Comprehensive end-to-end automated test for ANNA Hospital System with PostgreSQL 18.6."""

from __future__ import annotations

import sys
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def run_tests():
    print("==================================================")
    print("RUNNING ANNA SYSTEM END-TO-END VERIFICATION")
    print("==================================================")

    # 1. Test Receptionist Stats
    print("\n[1/8] Testing Receptionist Stats...")
    res = client.get("/api/receptionist/stats")
    assert res.status_code == 200, f"Failed: {res.text}"
    stats = res.json()
    print("Reception Stats:", stats)
    assert stats["total_beds"] == 20, "Total beds should be 20"
    assert stats["active_patients"] > 0, "Should have active patients"

    # 2. Test Beds List
    print("\n[2/8] Testing Ward Beds List...")
    res = client.get("/api/beds")
    assert res.status_code == 200
    beds = res.json()
    assert len(beds) == 20, f"Expected 20 beds, got {len(beds)}"
    occupied_count = sum(1 for b in beds if b["is_occupied"])
    print(f"Verified 20 beds ({occupied_count} occupied, {20 - occupied_count} available)")

    # 3. Test Clinician Stats & Patients List
    print("\n[3/8] Testing Clinician Stats & Roster...")
    res = client.get("/api/clinician/stats")
    assert res.status_code == 200
    c_stats = res.json()
    print("Clinician Stats:", c_stats)

    res = client.get("/api/patients?active_only=true")
    assert res.status_code == 200
    patients = res.json()
    assert len(patients) > 0, "Active patients list should not be empty"
    first_patient = patients[0]
    print(f"Sample Patient: {first_patient['full_name']} ({first_patient['patient_code']}) - Bed {first_patient['bed_number']} - Risk: {first_patient['risk_level']}")
    assert first_patient["latest_vitals"] is not None, "Latest vitals should be populated"

    # 4. Test Deep Analytics
    print("\n[4/8] Testing Patient Deep Analytics...")
    p_code = first_patient["patient_code"]
    res = client.get(f"/api/patients/{p_code}/analytics?days=30")
    assert res.status_code == 200
    analytics = res.json()
    assert len(analytics["vitals_series"]) > 0, "Vitals time series should be present"
    assert len(analytics["wellness_responses"]) > 0, "Wellness responses should be present"
    assert len(analytics["summaries"]) > 0, "Medical summaries should be present"
    print(f"Analytics verified: {len(analytics['vitals_series'])} vitals points, {len(analytics['wellness_responses'])} responses, {len(analytics['summaries'])} summaries.")

    # 5. Test Doctor Task Assignment
    print("\n[5/8] Testing Task Assignment...")
    task_payload = {
        "patient_code": p_code,
        "task_type": "ANNA Health Check",
        "instructions": "Test checkup assignment.",
        "priority": "urgent",
    }
    res = client.post("/api/tasks", json=task_payload)
    assert res.status_code == 200
    task = res.json()
    task_id = task["id"]
    print(f"Created task #{task_id} with priority '{task['priority']}' and status '{task['status']}'")

    # 6. Test Robot Task Claim & Completion
    print("\n[6/8] Testing Robot Controller Task Claim & Complete...")
    headers = {"X-Anna-Robot-Key": "change-robot-key"}
    claim_res = client.post("/api/robot/tasks/next", headers=headers)
    assert claim_res.status_code == 200
    claimed = claim_res.json()
    assert claimed["status"] == "in_progress"
    print(f"Robot successfully claimed task #{claimed['id']} (status: {claimed['status']})")

    complete_payload = {
        "status": "completed",
        "temperature_c": "37.2 C",
        "pulse_bpm": "78 BPM",
        "spo2_percent": "98.5%",
        "ecg_note": "Normal Sinus Rhythm",
        "emotion": "Happy",
        "answers": {
            "Sleep Hours": "7 hours",
            "Water Intake": "6 glasses",
            "Pain/Discomfort": "None",
            "Appetite": "Normal",
            "Exercise Today": "Yes",
            "Stress Level": "3",
        },
        "clinical_summary": "Test automated assessment complete. Vitals normal. Requires clinician review; prototype readings are not diagnostic.",
        "patient_summary": f"Hello {first_patient['full_name']}! ANNA finished your health checkup. Your temperature and pulse are steady!",
    }
    comp_res = client.post(f"/api/robot/tasks/{claimed['id']}/complete", json=complete_payload, headers=headers)
    assert comp_res.status_code == 200
    assert comp_res.json()["ok"] is True
    print(f"Robot successfully completed task #{claimed['id']} with dual report generation.")

    # 7. Test Patient Portal Auth & Features
    print("\n[7/8] Testing Patient Portal Flow...")
    login_payload = {
        "patient_code": p_code,
        "portal_pin": "123456",
    }
    portal_res = client.post("/api/portal/auth/login", json=login_payload)
    assert portal_res.status_code == 200, f"Portal login failed: {portal_res.text}"
    print(f"Patient {p_code} authenticated into Portal successfully.")

    # Check History & Vitals
    vitals_res = client.get("/api/portal/vitals")
    assert vitals_res.status_code == 200
    history_res = client.get("/api/portal/history")
    assert history_res.status_code == 200
    assert len(history_res.json()) > 0
    print(f"Patient successfully fetched {len(history_res.json())} friendly history records.")

    # 8. Test Alert Acknowledgment
    print("\n[8/8] Testing Alert Center...")
    alerts_res = client.get("/api/alerts?status=active")
    assert alerts_res.status_code == 200
    alerts = alerts_res.json()
    assert len(alerts) > 0, "There should be active alerts"
    test_alert = alerts[0]
    ack_res = client.post(f"/api/alerts/{test_alert['id']}/acknowledge", json={"note": "Evaluated bedside."})
    assert ack_res.status_code == 200
    print(f"Acknowledged alert #{test_alert['id']} with clinical note.")

    print("\n==================================================")
    print("ALL 8 END-TO-END TESTS PASSED ON POSTGRESQL 18.6!")
    print("==================================================")


if __name__ == "__main__":
    run_tests()
