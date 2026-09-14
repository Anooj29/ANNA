# 🤖 Project ANNA: AI Healthcare Assistant Robot

ANNA is an integrated healthcare system consisting of a Raspberry Pi-powered robot and a suite of FastAPI dashboards. The system automates patient registration, bed assignment, and autonomous health monitoring through a combination of computer vision, local voice processing, and a centralized PostgreSQL database.

## 🏗️ System Architecture

The system follows a **Hub-and-Spoke** model where the Windows PC (Hub) manages the data and the Raspberry Pi (Spoke) executes the physical interactions.

### Component Map
- **Receptionist Dashboard** (Port 8001): Registers patients and captures reference photos.
- **Doctor's Dashboard** (Port 8002): Manages patient assignments and activates the robot.
- **Patient Dashboard** (Port 8003): Provides patient-facing health data.
- **PostgreSQL Database** (Docker): The single source of truth for all patient and session data.
- **Healthcare Robot** (Raspberry Pi): Performs face recognition, sensor readings, and voice interaction.

### The "Automatic Face Sync" Pipeline
To avoid manual file transfers, ANNA implements a delta-sync system:
1. **Registration**: Photo is saved on the Laptop.
2. **DB Entry**: Patient record is created in PostgreSQL.
3. **Detection**: The Robot polls the DB every 30 seconds for new registrations.
4. **Sync**: The Robot downloads new photos via the Receptionist Dashboard's static API.
5. **Match**: The Robot updates its local face database in real-time.

---

## 🚀 Getting Started

### 1. Prerequisites
- **Windows PC**: Docker Desktop (with WSL2 enabled), Python 3.11+.
- **Raspberry Pi**: Python 3.11+, Camera Module, GPIO sensors.
- **Network**: Both devices must be on the same local network.

### 2. Setup (Laptop)
**A. Database Startup**
```powershell
# Start PostgreSQL via Docker
docker compose up -d postgres

# Initialize database tables and seed 20 beds
& .\.venv-dashboard\Scripts\python.exe -m dashboards.init_db
```

**B. Launch Dashboards** (Run each in a separate terminal)
```powershell
# Receptionist
& .\.venv-dashboard\Scripts\python.exe -m uvicorn dashboards.receptionist.main:app --host 0.0.0.0 --port 8001

# Doctor
& .\.venv-dashboard\Scripts\python.exe -m uvicorn dashboards.doctor.main:app --host 0.0.0.0 --port 8002

# Patient
& .\.venv-dashboard\Scripts\python.exe -m uvicorn dashboards.patient.main:app --host 0.0.0.0 --port 8003
```

### 3. Setup (Robot - Raspberry Pi)
```bash
# Navigate to project
cd ~/dishant/ANNA

# Ensure the robot knows the laptop's IP
export POSTGRES_HOST=192.168.x.x  # Replace with your laptop's IP

# Run the robot
./run.sh
```

---

## 🛠️ Operational Workflow

### Step 1: Registration
The Receptionist registers a patient $\rightarrow$ Captures photo $\rightarrow$ Assigns a bed. The system automatically stores the record in Postgres and the photo on the laptop.

### Step 2: Activation
The robot starts in `IDLE` state (stationary). The Doctor opens the portal (`http://localhost:8002`) and clicks **"🚀 Start Robot"**. The robot then enters `SEARCH` mode.

### Step 3: Interaction
1. **Recognition**: The robot identifies a registered patient's face.
2. **Greeting**: The robot greets the patient using a Gemini-powered emotional greeting.
3. **Health Check**: After the patient says *"yes buddy"*, the robot:
    - Reads Temperature, Pulse, and ECG sensors.
    - Asks a series of health questions.
    - Generates a health summary using Gemini.
4. **Completion**: Session data is saved, and the robot returns to search for the next patient.

---

## 📋 Technical Specifications

### Robot State Machine
| State | Description | Trigger to Next State |
| :--- | :--- | :--- |
| `IDLE` | Stationary, waiting for command | "Start Robot" command $\rightarrow$ `SEARCH` |
| `SEARCH` | Looking for known faces | Face Match $\rightarrow$ `INTERACT` |
| `INTERACT` | Greeting and confirming | "yes buddy" $\rightarrow$ `HEALTH_CHECK` |
| `HEALTH_CHECK` | Sensor readings & Questions | All questions answered $\rightarrow$ `DONE` |
| `DONE` | Saving data & resetting | Timer expire $\rightarrow$ `SEARCH` |

### Network Ports
- **8001**: Receptionist API & Photo Server
- **8002**: Doctor API
- **8003**: Patient API
- **5000**: Robot Telemetry (TCP)
- **5432**: PostgreSQL Database
