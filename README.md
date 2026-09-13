# Anna - Healthcare Assistant Robot

A Raspberry Pi robot that finds a person, recognises them by face, and walks
them through a short guided health check (temperature, pulse, ECG, and a
few spoken questions), then gives a friendly Gemini-generated wellness
summary. Status is streamed to a companion laptop/dashboard over TCP.

## 🌟 Key Features
- **Autonomous Navigation**: Vision-based person tracking and approach.
- **Identity & Emotion**: Local face recognition (dlib) and emotion detection (TFLite).
- **Local Voice Interaction**: Fully local Speech-to-Text (Vosk) and Text-to-Speech (Piper) for zero-latency communication.
- **Integrated Health Monitoring**: Real-time temperature, pulse, and ECG readings.
- **AI Health Summaries**: Synthesis of vitals and survey answers via Google Gemini AI.
- **Centralized Management**: Three interconnected dashboards for Receptionists, Doctors, and Patients.

## ⚠️ SAFETY / MEDICAL DISCLAIMER
This is a hobby / prototype project. It does not perform medical diagnosis.
The "ECG" reading is a coarse heart-rhythm-regularity estimate computed from
a single analog channel, and the pulse reading is **simulated** because no
real pulse sensor is wired up yet. Neither is a substitute for a real
medical device or a professional evaluation.

## 🛠️ Hardware
- Raspberry Pi (any model with a camera and GPIO header)
- USB or CSI camera
- HC-SR04 ultrasonic distance sensor
- L298N-style dual motor driver driving two DC motors
- DS18B20 1-Wire temperature probe
- ADS1115 ADC + AD8232-style single-lead ECG front-end
- Speaker and Microphone (for local voice interaction)

## 📂 Project Layout
```
anna_robot/
├── CMakeLists.txt        # Build/run wrapper for robot and dashboards
├── requirements.txt      # Robot Python dependencies (includes Vosk/Piper)
├── requirements-dashboard.txt # Dashboard Python dependencies
├── run.sh                # One-command robot launcher
├── models/                # TFLite models (person, emotion)
├── known_faces/           # Patient reference photos
└── anna_robot/            # Core Python package
    ├── main.py             # Entry point
    ├── robot.py            # State machine (handles local voice & TCP commands)
    ├── perception/         # Face ID, Person Detection, Speech Recognition
    └── voice.py            # Piper TTS wrapper
```

## 📊 Dashboards
The system includes three dashboards sharing one Postgres database:
1. **Receptionist** (Port 8001) - Registers patients, captures photos, and assigns beds.
2. **Doctor** (Port 8002) - Reviews health records and assigns ANNA to visit patients.
3. **Patient** (Port 8003) - Secure portal for patients to view their own wellness reports.

## 🚀 Setup and Run

### 1. The Robot (on Raspberry Pi)
```bash
# Install system deps
sudo apt update
sudo apt install -y cmake build-essential libopenblas-dev liblapack-dev \
                     libatlas-base-dev espeak python3-venv python3-dev \
                     portaudio19-dev

# Run the robot
./run.sh
```

### 2. The Dashboards (on PC)
```powershell
# Setup venv and DB
python -m venv .venv-dashboard
.venv-dashboard\Scripts\python.exe -m pip install -r requirements-dashboard.txt
docker compose up -d postgres
.venv-dashboard\Scripts\python.exe -m dashboards.init_db

# Start a dashboard (e.g. Doctor)
.venv-dashboard\Scripts\python.exe -m uvicorn dashboards.doctor.main:app --host 0.0.0.0 --port 8002
```

## ⚙️ Configuration
Configuration is environment-driven (see `.env.example`). Key variables include:
- `GEMINI_API_KEY`: Your Google AI key.
- `ROBOT_VOSK_MODEL`: Path to the Vosk STT model.
- `ROBOT_PIPER_BIN` / `ROBOT_PIPER_MODEL`: Paths to the Piper TTS system.
- `POSTGRES_HOST`: The IP address of the PC running the database.
