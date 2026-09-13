# Anna - Healthcare Assistant Robot

A Raspberry Pi robot that finds a person, recognises them by face, and walks
them through a short guided health check (temperature, pulse, ECG, and a
few spoken questions), then gives a friendly Gemini-generated wellness
summary. Status is streamed to a companion laptop/dashboard over TCP.

## SAFETY / MEDICAL DISCLAIMER

This is a hobby / prototype project. It does not perform medical diagnosis.
The "ECG" reading is a coarse heart-rhythm-regularity estimate computed from
a single analog channel, and the pulse reading is **simulated** because no
real pulse sensor is wired up yet. Neither is a substitute for a real
medical device or a professional evaluation, and nothing this program
outputs should be presented to a patient as a diagnosis.

## Hardware

- Raspberry Pi (any model with a camera and GPIO header)
- USB or CSI camera
- HC-SR04 ultrasonic distance sensor
- L298N-style dual motor driver (or similar) driving two DC motors
- DS18B20 1-Wire temperature probe
- ADS1115 ADC + AD8232-style single-lead ECG front-end
- Speaker (for TTS)

Default GPIO pin assignments (BCM numbering) live in `anna_robot/config.py`
and can be overridden with environment variables - see below.

## Project layout

```
anna_robot/
├── CMakeLists.txt        # optional build/run/install wrapper (see below)
├── requirements.txt      # all Python dependencies
├── run.sh                # one-command launcher (venv + pip install + run)
├── models/                # put person_detect.tflite + emotion_model.tflite here
├── known_faces/           # one sub-folder of reference photos per patient
└── anna_robot/            # the Python package
    ├── main.py             # CLI entry point
    ├── robot.py            # the state machine that ties everything together
    ├── config.py           # environment-driven configuration
    ├── state.py            # RobotState / HealthStage enums + questionnaire
    ├── patient_session.py  # per-patient session data
    ├── gemini_assistant.py # Gemini greetings + wellness summaries
    ├── voice.py            # text-to-speech
    ├── telemetry.py        # JSON-over-TCP link to a companion device
    ├── motors.py           # differential-drive motor control
    ├── sensors/            # ultrasonic, temperature, pulse, ECG
    └── perception/         # person detection, face ID, emotion detection
```

## System packages (Raspberry Pi OS / Debian-based)

`dlib` (used by `face_recognition`) and `pyttsx3` need a few system packages
before the Python dependencies will build/run cleanly:

```bash
sudo apt update
sudo apt install -y cmake build-essential libopenblas-dev liblapack-dev \
                     libatlas-base-dev espeak python3-venv python3-dev
```

## Setup and run

### Option A - the run script (simplest)

```bash
export GEMINI_API_KEY="your-key-here"   # optional but recommended
./run.sh
```

`run.sh` creates a `.venv`, installs `requirements.txt` into it, checks that
the model files and `known_faces/` exist, and then starts the robot. Pass
`--no-debug-window` for a headless run, or set `SKIP_INSTALL=1` to skip the
dependency step on subsequent runs.

### Option B - CMake

```bash
mkdir build && cd build
cmake ..
cmake --build . --target deps    # create .venv + install requirements.txt
cmake --build . --target check   # quick syntax check, no hardware needed
cmake --build . --target run     # start the robot
```

`cmake --install . --prefix /opt` copies a deployable copy of the package,
`models/`, `known_faces/`, `requirements.txt` and `run.sh` to
`/opt/share/anna_robot`.

### Option C - manual

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m anna_robot.main
```

## Configuration

Everything is overridable via environment variables (sane defaults match
the original hardware):

| Variable                        | Default                          | Meaning                                   |
|----------------------------------|-----------------------------------|--------------------------------------------|
| `GEMINI_API_KEY`                 | *(none)*                          | Gemini API key; falls back to canned text if unset |
| `GEMINI_MODEL`                   | `models/gemini-flash-latest`      | Gemini model name                          |
| `ROBOT_TCP_PORT`                 | `5000`                            | Telemetry TCP port                         |
| `ROBOT_DISTANCE_TRIGGER_CM`      | `60.0`                            | Distance at which the robot stops and greets |
| `ROBOT_SAFETY_STOP_CM`           | `20.0`                            | Minimum safe following distance            |
| `ROBOT_PERSON_THRESHOLD`         | `0.65`                            | Person-detection confidence threshold      |
| `ROBOT_FACE_MATCH_THRESHOLD`     | `0.45`                            | Face-match distance threshold (lower = stricter) |
| `ROBOT_PERSON_CONFIRM_FRAMES`    | `3`                               | Consecutive frames needed to confirm a person |
| `ROBOT_MAX_UNKNOWN_ATTEMPTS`     | `3`                               | Unknown-face attempts before giving up     |
| `ROBOT_MAX_NO_FACE_FRAMES`       | `150`                             | Frames with no face before returning to search |
| `ROBOT_PERSON_MODEL`             | `models/person_detect.tflite`     | Path to the person-detection model         |
| `ROBOT_EMOTION_MODEL`            | `models/emotion_model.tflite`     | Path to the emotion model                  |
| `ROBOT_KNOWN_FACES_DIR`          | `known_faces`                     | Reference-photo directory                  |
| `ROBOT_TTS_RATE`                 | `145`                             | Speech rate (words/min)                    |
| `ROBOT_TTS_REINIT_EACH_CALL`     | `true`                            | Recreate the TTS engine per utterance (avoids a known espeak hang) |
| `ROBOT_SHOW_DEBUG_WINDOW`        | `true`                            | Show the OpenCV preview window             |
| `ROBOT_LOG_LEVEL`                | `INFO`                            | Logging verbosity                          |

CLI flags (`--port`, `--log-level`, `--no-debug-window`) take priority over
the environment variables above.

## Hospital software application

The hospital software is separate from `anna_robot/`. It uses the central
FastAPI entry point `backend.app.main`, shared SQLAlchemy models, Alembic
migrations, and **PostgreSQL only**. It serves the receptionist, clinician,
and patient interfaces at `/receptionist`, `/clinician`, and `/patient`.
Robot hardware and navigation stay in the robot package; the hospital app
communicates with it through authenticated `/api/robot/*` endpoints.

### Run on Windows

1. Install PostgreSQL and create the configured database/user, or run the
   PostgreSQL service in `docker-compose.yml`.
2. Copy `.env.example` to `.env`. Set `POSTGRES_*`,
   `DASHBOARD_SESSION_SECRET`, and `ROBOT_API_KEY` to private values.
3. Set up dependencies once:

   ```powershell
   py -3.12 -m venv .venv-dashboard
   .venv-dashboard\Scripts\python.exe -m pip install -r requirements-dashboard.txt
   ```

4. Double-click `run.bat`, or run it from a terminal. Open
   [http://127.0.0.1:8000](http://127.0.0.1:8000) on this computer. For a phone
   on the same Wi-Fi, use the `http://<Wi-Fi IPv4 address>:8000` URL printed by
   the launcher. Keep the launcher window open. If Windows prompts for network
   access, allow Python on private networks. Guest Wi-Fi or client isolation
   may prevent phones from reaching other devices on the network.

`run.bat` applies migrations, ensures the configured bed pool, and starts
the central server. It does not seed demonstration patients or credentials.
For an **existing unversioned** database, first follow
[database/MIGRATIONS.md](database/MIGRATIONS.md) to back up and rehearse
the migration. The launcher deliberately refuses an unversioned schema.

### Demo and validation

`database.seed_data` is restricted to an empty database and requires
`SEED_DOCTOR_PASSWORD`, `SEED_RECEPTION_PASSWORD`, and
`SEED_PATIENT_PIN` in the environment. It creates fictional demonstration
records; never run it against patient data. Generated demo checkups require
`ENABLE_DEMO_SIMULATION=true`, remain labelled simulated, and are excluded
from clinical trends and threshold alerts.

The test suite uses disposable PostgreSQL databases and does not write to
the configured hospital database:

```powershell
.venv-dashboard\Scripts\python.exe -m unittest discover -s tests -v
node --check dashboards/clinician/static/app.js
```

`/api/health` shows process health; `/api/ready` verifies PostgreSQL and
migration revision. Clinician reports can be printed from Patient Workspace
or exported as operations CSV. Alert thresholds and estimate assumptions are
configured in `.env.example`. ANNA observations are assistive screening
signals and require clinician review.

## Notes on the companion telemetry link

The robot listens on `ROBOT_TCP_PORT` and blocks at startup until exactly
one companion client connects; it then streams a JSON status packet every
control-loop iteration and reads back any voice-command text the companion
app forwards (e.g. "yes buddy", "check temperature", question answers).
