# 🤖 Project ANNA - Current Status Report
**Last Updated:** 2026-09-13

## 🎯 Current Goal
Get the PostgreSQL database running on the Windows PC using Docker so the dashboards and robot can sync data.

## 🛠️ What has been completed:
1.  **Robot Implementation**: 
    - Local Speech-to-Text (Vosk) integrated.
    - Local Text-to-Speech (Piper) integrated.
    - Robot priority set to Local Voice $\rightarrow$ Network Commands.
    - Robot successfully launched on Raspberry Pi.
2.  **Dashboard Implementation**:
    - Receptionist, Doctor, and Patient dashboards created (FastAPI).
    - Common database models (`Patient`, `Bed`, `PatientSession`, `Assignment`) defined.
3.  **Deployment Setup**:
    - Code pushed to GitHub.
    - Robot cloned and environment set up on Raspberry Pi.

## 🚧 The Current Roadblock (Where we stopped)
- **Issue**: Docker Desktop is installed on Windows, but cannot start because **WSL (Windows Subsystem for Linux)** is not installed/enabled.
- **Error**: `dockeer destop showinfgwsl not installed`

## ⏭️ Next Steps (Immediate Action Plan):
1.  **Run `wsl --install`** in an Administrator PowerShell.
2.  **Restart the computer** (Mandatory to enable Virtualization).
3.  **Open Docker Desktop** and wait for the whale icon to turn green (Engine Running).
4.  **Start Database**: Run `docker compose up -d postgres` in the project root.
5.  **Initialize DB**: Run `.venv-dashboard\Scripts\python.exe -m dashboards.init_db`.
6.  **Launch Dashboards**: Run the `uvicorn` commands for Receptionist, Doctor, and Patient.

## 📍 Key Locations:
- **Robot Code**: `~/dishant/ANNA` (on Raspberry Pi)
- **Dashboards/DB**: `C:\Users\bavis\OneDrive\Desktop\anna` (on Windows PC)
