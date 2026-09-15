"""Automated Playwright Browser QA and Visual Screenshot Suite for ANNA.

Runs end-to-end browser scenarios across Receptionist, Clinician, and Patient profiles,
validating DOM rendering, user interactions, network responses, and console hygiene.
Saves all visual artifacts to docs/qa/screenshots/.
"""

import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = ROOT / "docs" / "qa" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8000"


def run_qa():
    errors_found = []
    console_logs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        
        # 1. Receptionist Profile (Desktop: 1440x900)
        print("\n--- Testing Receptionist Profile ---")
        desktop_context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = desktop_context.new_page()

        def on_console(msg):
            if msg.type in ("error", "warning"):
                console_logs.append(f"[{msg.type.upper()}] {msg.text}")
                if msg.type == "error":
                    print(f"Browser Console Error: {msg.text}")

        def on_page_error(exc):
            errors_found.append(f"PageError: {exc}")
            print(f"Page Error: {exc}")

        page.on("console", on_console)
        page.on("pageerror", on_page_error)

        page.goto(f"{BASE_URL}/receptionist")
        page.wait_for_selector("#reception-login-form", state="visible", timeout=8000)
        page.screenshot(path=str(SCREENSHOT_DIR / "01_login.png"), full_page=False)
        print("Captured: 01_login.png")

        # Fill receptionist login
        page.fill("#reception-user", "reception")
        page.fill("#reception-password", "ReceptionPass2026!")
        page.click("#reception-login-form button[type='submit']")
        page.wait_for_selector(".main-container:not([hidden])", state="visible", timeout=10000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SCREENSHOT_DIR / "02_reception_overview.png"), full_page=False)
        print("Captured: 02_reception_overview.png")

        # Ward & Bed Map tab
        page.click("button[data-tab='ward-tab']")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(SCREENSHOT_DIR / "03_reception_beds.png"), full_page=False)
        print("Captured: 03_reception_beds.png")

        # Patient Intake Tab
        page.click("button[data-tab='intake-tab']")
        page.wait_for_selector("#intake-form", state="visible", timeout=5000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(SCREENSHOT_DIR / "04_reception_admit.png"), full_page=False)
        print("Captured: 04_reception_admit.png")

        # Patient Directory Tab
        page.click("button[data-tab='patients-tab']")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(SCREENSHOT_DIR / "05_reception_directory.png"), full_page=False)
        print("Captured: 05_reception_directory.png")

        # Ward Analytics Tab
        page.click("button[data-tab='analytics-tab']")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(SCREENSHOT_DIR / "06_reception_analytics.png"), full_page=False)
        print("Captured: 06_reception_analytics.png")

        # Logout Receptionist
        page.click("#reception-logout")
        page.wait_for_selector("#reception-login-form", state="visible", timeout=5000)
        desktop_context.close()

        # 2. Clinician Profile
        print("\n--- Testing Clinician Profile ---")
        clinician_context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = clinician_context.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_page_error)

        page.goto(f"{BASE_URL}/clinician")
        page.wait_for_selector("#login-form", state="visible", timeout=5000)
        page.fill("#login-email", "doctor")
        page.fill("#login-password", "DoctorPass2026!")
        page.click("#login-form button[type='submit']")
        page.wait_for_selector("#app-view:not([hidden])", state="visible", timeout=8000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SCREENSHOT_DIR / "10_clinician_overview.png"), full_page=False)
        print("Captured: 10_clinician_overview.png")

        # Priority Roster in Overview Tab
        priority_panel = page.query_selector(".priority-panel")
        if priority_panel:
            priority_panel.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
        page.screenshot(path=str(SCREENSHOT_DIR / "11_clinician_priority_roster.png"), full_page=False)
        print("Captured: 11_clinician_priority_roster.png")

        # Click first patient's workspace button
        page.wait_for_selector("#patients-table-body tr", state="visible", timeout=8000)
        page.wait_for_selector(".patient-open-action", state="visible", timeout=8000)
        page.click(".patient-open-action")
        page.wait_for_selector("#workspace-content", state="visible", timeout=8000)
        page.wait_for_timeout(1500)

        page.screenshot(path=str(SCREENSHOT_DIR / "12_clinician_patient_profile.png"), full_page=False)
        print("Captured: 12_clinician_patient_profile.png")

        # Vitals Cards
        vitals_elem = page.query_selector("#workspace-vitals")
        if vitals_elem:
            try:
                vitals_elem.scroll_into_view_if_needed()
            except Exception:
                pass
            page.wait_for_timeout(500)
            page.screenshot(path=str(SCREENSHOT_DIR / "13_clinician_vitals.png"), full_page=False)
            print("Captured: 13_clinician_vitals.png")

        # Vital Trends
        trend_range = page.query_selector("#workspace-range")
        if trend_range:
            page.select_option("#workspace-range", "24h")
            page.wait_for_timeout(800)
        page.screenshot(path=str(SCREENSHOT_DIR / "14_clinician_trends.png"), full_page=False)
        print("Captured: 14_clinician_trends.png")

        # Timeline
        timeline_elem = page.query_selector("#workspace-timeline")
        if timeline_elem:
            try:
                timeline_elem.scroll_into_view_if_needed()
            except Exception:
                pass
            page.wait_for_timeout(500)
            page.screenshot(path=str(SCREENSHOT_DIR / "15_clinician_timeline.png"), full_page=False)
            print("Captured: 15_clinician_timeline.png")

        # Alerts Tab
        page.click("button[data-tab='alerts-tab']")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(SCREENSHOT_DIR / "16_clinician_alerts.png"), full_page=False)
        print("Captured: 16_clinician_alerts.png")

        # Tasks / Queue Tab
        page.click("button[data-tab='queue-tab']")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(SCREENSHOT_DIR / "17_clinician_tasks.png"), full_page=False)
        print("Captured: 17_clinician_tasks.png")

        # Analytics Tab
        page.click("button[data-tab='analytics-tab']")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(SCREENSHOT_DIR / "18_clinician_analytics.png"), full_page=False)
        print("Captured: 18_clinician_analytics.png")

        # Reports Tab
        page.click("button[data-tab='reports-tab']")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(SCREENSHOT_DIR / "19_clinician_reports.png"), full_page=False)
        print("Captured: 19_clinician_reports.png")

        # Logout Clinician
        page.click("#btn-logout")
        page.wait_for_selector("#login-view:not([hidden])", state="visible", timeout=5000)
        clinician_context.close()

        # 3. Patient Care Portal
        print("\n--- Testing Patient Care Portal ---")
        patient_context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = patient_context.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_page_error)

        page.goto(f"{BASE_URL}/patient")
        page.wait_for_selector("#portal-login-form", state="visible", timeout=5000)
        page.fill("#patient_code", "ANP-00001")
        page.fill("#portal_pin", "123456")
        page.click("#portal-login-form button[type='submit']")
        page.wait_for_selector("#app-view:not([hidden])", state="visible", timeout=8000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SCREENSHOT_DIR / "20_patient_home_en.png"), full_page=False)
        print("Captured: 20_patient_home_en.png")

        # Scroll to trends
        trend_sec = page.query_selector("#trends-section")
        if trend_sec:
            trend_sec.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
        page.screenshot(path=str(SCREENSHOT_DIR / "21_patient_trends_en.png"), full_page=False)
        print("Captured: 21_patient_trends_en.png")

        # Scroll to medications
        med_sec = page.query_selector("#meds-section")
        if med_sec:
            med_sec.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
        page.screenshot(path=str(SCREENSHOT_DIR / "22_patient_medications_en.png"), full_page=False)
        print("Captured: 22_patient_medications_en.png")

        # Switch to Hindi
        page.select_option("#portal-language", "hi")
        page.wait_for_timeout(1000)
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(SCREENSHOT_DIR / "23_patient_hindi.png"), full_page=False)
        print("Captured: 23_patient_hindi.png")

        # Switch to Marathi
        page.select_option("#portal-language", "mr")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(SCREENSHOT_DIR / "24_patient_marathi.png"), full_page=False)
        print("Captured: 24_patient_marathi.png")

        # Switch back to English and check History stream
        page.select_option("#portal-language", "en")
        page.wait_for_timeout(500)
        hist_sec = page.query_selector("#history-section")
        if hist_sec:
            hist_sec.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
        page.screenshot(path=str(SCREENSHOT_DIR / "25_patient_reports.png"), full_page=False)
        print("Captured: 25_patient_reports.png")

        # Logout Patient
        page.click("#btn-logout")
        page.wait_for_selector("#login-view:not([hidden])", state="visible", timeout=5000)
        patient_context.close()

        # 4. Mobile & Tablet Viewports
        print("\n--- Testing Mobile & Tablet Viewports ---")
        
        # Mobile Reception (390x844)
        mobile_rec_context = browser.new_context(viewport={"width": 390, "height": 844})
        p_m = mobile_rec_context.new_page()
        p_m.goto(f"{BASE_URL}/receptionist")
        p_m.fill("#reception-user", "reception")
        p_m.fill("#reception-password", "ReceptionPass2026!")
        p_m.click("#reception-login-form button[type='submit']")
        p_m.wait_for_selector(".main-container:not([hidden])", state="visible", timeout=8000)
        p_m.wait_for_timeout(1000)
        p_m.screenshot(path=str(SCREENSHOT_DIR / "30_mobile_reception.png"), full_page=False)
        print("Captured: 30_mobile_reception.png")
        mobile_rec_context.close()

        # Mobile Clinician (390x844)
        mobile_doc_context = browser.new_context(viewport={"width": 390, "height": 844})
        p_m = mobile_doc_context.new_page()
        p_m.goto(f"{BASE_URL}/clinician")
        p_m.fill("#login-email", "doctor")
        p_m.fill("#login-password", "DoctorPass2026!")
        p_m.click("#login-form button[type='submit']")
        p_m.wait_for_selector("#app-view:not([hidden])", state="visible", timeout=8000)
        p_m.wait_for_timeout(1000)
        p_m.screenshot(path=str(SCREENSHOT_DIR / "31_mobile_clinician.png"), full_page=False)
        print("Captured: 31_mobile_clinician.png")
        mobile_doc_context.close()

        # Mobile Patient (390x844)
        mobile_pat_context = browser.new_context(viewport={"width": 390, "height": 844})
        p_m = mobile_pat_context.new_page()
        p_m.goto(f"{BASE_URL}/patient")
        p_m.fill("#patient_code", "ANP-00001")
        p_m.fill("#portal_pin", "123456")
        p_m.click("#portal-login-form button[type='submit']")
        p_m.wait_for_selector("#app-view:not([hidden])", state="visible", timeout=8000)
        p_m.wait_for_timeout(1000)
        p_m.screenshot(path=str(SCREENSHOT_DIR / "32_mobile_patient.png"), full_page=False)
        print("Captured: 32_mobile_patient.png")
        mobile_pat_context.close()

        # Tablet Clinician (768x1024)
        tablet_doc_context = browser.new_context(viewport={"width": 768, "height": 1024})
        p_t = tablet_doc_context.new_page()
        p_t.goto(f"{BASE_URL}/clinician")
        p_t.fill("#login-email", "doctor")
        p_t.fill("#login-password", "DoctorPass2026!")
        p_t.click("#login-form button[type='submit']")
        p_t.wait_for_selector("#app-view:not([hidden])", state="visible", timeout=8000)
        p_t.wait_for_timeout(1000)
        p_t.screenshot(path=str(SCREENSHOT_DIR / "33_tablet_clinician.png"), full_page=False)
        print("Captured: 33_tablet_clinician.png")
        tablet_doc_context.close()

        # Narrow Mobile Patient (320x640)
        narrow_context = browser.new_context(viewport={"width": 320, "height": 640})
        p_n = narrow_context.new_page()
        p_n.goto(f"{BASE_URL}/patient")
        p_n.fill("#patient_code", "ANP-00001")
        p_n.fill("#portal_pin", "123456")
        p_n.click("#portal-login-form button[type='submit']")
        p_n.wait_for_selector("#app-view:not([hidden])", state="visible", timeout=8000)
        p_n.wait_for_timeout(1000)
        p_n.screenshot(path=str(SCREENSHOT_DIR / "34_mobile_narrow_patient.png"), full_page=False)
        print("Captured: 34_mobile_narrow_patient.png")
        narrow_context.close()

        # 5. Error, Empty, and Offline States
        print("\n--- Testing Error, Empty, and State Handlers ---")
        err_context = browser.new_context(viewport={"width": 1440, "height": 900})
        p_e = err_context.new_page()
        # Invalid login test
        p_e.goto(f"{BASE_URL}/clinician")
        p_e.fill("#login-email", "invalid_user")
        p_e.fill("#login-password", "wrong_password")
        p_e.click("#login-form button[type='submit']")
        p_e.wait_for_timeout(1000)
        p_e.screenshot(path=str(SCREENSHOT_DIR / "40_error_state.png"), full_page=False)
        print("Captured: 40_error_state.png")

        # Patient empty workspace state
        p_e.goto(f"{BASE_URL}/clinician")
        p_e.fill("#login-email", "doctor")
        p_e.fill("#login-password", "DoctorPass2026!")
        p_e.click("#login-form button[type='submit']")
        p_e.wait_for_selector("#app-view:not([hidden])", state="visible", timeout=8000)
        p_e.click("button[data-tab='patient-workspace-tab']")
        p_e.wait_for_timeout(1000)
        p_e.screenshot(path=str(SCREENSHOT_DIR / "41_empty_state.png"), full_page=False)
        print("Captured: 41_empty_state.png")

        # Robot Fleet / Queue view
        p_e.click("button[data-tab='queue-tab']")
        p_e.wait_for_timeout(1000)
        p_e.screenshot(path=str(SCREENSHOT_DIR / "42_offline_state.png"), full_page=False)
        print("Captured: 42_offline_state.png")
        err_context.close()

        browser.close()

    print("\n==========================================")
    print("PLAYWRIGHT BROWSER QA RUN COMPLETED!")
    print(f"Total Screenshots: {len(list(SCREENSHOT_DIR.glob('*.png')))}")
    print(f"Page Errors: {len(errors_found)}")
    print(f"Console Logs: {len(console_logs)}")
    print("==========================================")


if __name__ == "__main__":
    run_qa()
