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

## Dashboards

The plan is three dashboards sharing one Postgres database:

1. **Receptionist** (built) - registers a patient (name, height, weight,
   blood group, a reference photo), assigns them a unique patient ID and a
   bed, saves the photo into `known_faces/` so ANNA can recognise them, and
   discharges patients to free their bed for reuse. Click any free bed on
   the ward map to assign it during intake; click any occupied bed to see
   who's in it and discharge them.
2. **Clinician** (not built yet) - doctor/nurse assigns ANNA a patient to
   visit; ANNA goes there and returns to its home position.
3. **Patient** (not built yet) - lets a patient view their own diagnosis
   reports.

They live in `dashboards/`, separate from the `anna_robot/` package,
with their own dependencies (`requirements-dashboard.txt`) and their own
virtual environment (`.venv-dashboard`) - these run on a regular PC at the
reception desk / nurse station, not the Raspberry Pi, so they deliberately
don't pull in `RPi.GPIO` / `tflite-runtime`. They also don't pull in
`dlib`/`face_recognition`: the intake form only needs to check "is there
one clear face in this photo?" before saving it, which plain OpenCV
handles with prebuilt wheels on every OS (Windows included) - no C++
build toolchain required on this machine. It checks with both frontal and
profile cascades (`dashboards/receptionist/face_check.py`) so a
slightly-turned or side-on photo isn't automatically rejected the way a
frontal-only check would reject it. Actually *identifying* whose face it
is still uses the real `face_recognition`/dlib library, but only on the
robot's side.

```
dashboards/
├── common/            # SQLAlchemy models + config shared by all 3 dashboards
├── receptionist/       # dashboard 1: FastAPI app + static frontend
│   ├── face_check.py    # "is there a face?" check (frontal + profile cascades)
│   └── static/          # plain HTML/CSS/JS - no build step
└── init_db.py          # creates tables, seeds the bed pool
```

### Running dashboard 1

By default the dashboard uses **SQLite** - a single file on disk, no
server to install or run. That's the right choice for developing/testing
on one machine, which is where you are right now:

```bash
cp .env.example .env      # DB_ENGINE=sqlite by default - nothing else to set up

mkdir build && cd build
cmake ..
cmake --build . --target receptionist
```

That one command creates `.venv-dashboard`, installs
`requirements-dashboard.txt` into it, creates/seeds the schema (a fresh
`anna_dashboard.db` file appears in the project root), and starts the
dashboard at **http://localhost:8001**. Re-running it later is safe - each
step only does work that hasn't already been done.

**Switching to Postgres**, once you actually have multiple dashboards on
different machines that need to share the same live data: set
`DB_ENGINE=postgres` in `.env`, fill in the `POSTGRES_*` values, then run
`cmake --build . --target db-up` first (starts Postgres via Docker if
installed) before `init-db` / `receptionist`. Nothing else in the code
changes - same models, same queries, same app.

Other useful targets: `cmake --build . --target db-up` /
`db-down` (Postgres only), `cmake --build . --target
init-db` (just create/seed the schema).

Manual equivalent, without CMake:

```bash
python3 -m venv .venv-dashboard && source .venv-dashboard/bin/activate
pip install -r requirements-dashboard.txt
python -m dashboards.init_db
uvicorn dashboards.receptionist.main:app --host 0.0.0.0 --port 8001
```

**On Windows:**

```powershell
python -m venv .venv-dashboard
.venv-dashboard\Scripts\python.exe -m pip install -r requirements-dashboard.txt
.venv-dashboard\Scripts\python.exe -m dashboards.init_db
.venv-dashboard\Scripts\python.exe -m uvicorn dashboards.receptionist.main:app --host 0.0.0.0 --port 8001
```

### Configuration

All new variables (on top of the robot's existing ones) live in
`.env.example`: `DB_ENGINE` (`sqlite` or `postgres`), `SQLITE_PATH`,
`POSTGRES_HOST/PORT/DB/USER/PASSWORD` (only read when `DB_ENGINE=postgres`),
`HOSPITAL_TOTAL_BEDS` (beds seeded on first run - raising it later is
safe, lowering it won't remove existing beds), `PATIENT_ID_PREFIX` (e.g.
`ANP` -> `ANP-00001`), and `RECEPTIONIST_PORT`.

### A known limitation worth knowing about

The robot currently treats the `known_faces/<folder name>` as the
patient's display name directly (see `known_faces/README.md`) - there's no
concept of "patient ID" inside `anna_robot/` yet. The receptionist
dashboard writes the patient's real database ID into Postgres regardless,
but ANNA itself won't know a patient's ID, height/weight/blood group, or
bed number until `anna_robot/perception/face_identifier.py` and
`robot.py` are wired up to read from this same database - a natural next
step once dashboard 2 (clinician) needs to look up patients by ID anyway.

## Notes on the companion telemetry link

The robot listens on `ROBOT_TCP_PORT` and blocks at startup until exactly
one companion client connects; it then streams a JSON status packet every
control-loop iteration and reads back any voice-command text the companion
app forwards (e.g. "yes buddy", "check temperature", question answers).
