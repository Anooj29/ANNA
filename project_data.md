# ANNA - Healthcare Assistant Robot: Comprehensive Project Documentation

---

## 1. Project Overview & Mission

**ANNA** (*Autonomous Nursing and Navigation Assistant*) is an end-to-end autonomous healthcare assistant robot prototype engineered for hospital ward environments. The project bridges physical robotics, on-device edge artificial intelligence, physiological sensor acquisition, large language models (LLMs), and modern web-based hospital administration portals.

### Primary Objectives
- **Autonomous Ward Interaction**: Detect human presence, approach safely, and recognize registered hospital patients using facial recognition.
- **Guided Health Checkups**: Walk patients through guided vital measurements (temperature, pulse, single-lead ECG) and spoken wellness questionnaires.
- **Empathetic AI Interactions**: Detect patient emotion (Happy, Sad, Angry, Neutral, Fear, Disgust, Surprise) and tailor conversational greetings and health summaries using **Google Gemini 1.5/Flash**.
- **Dual Clinical & Patient Reporting**: Generate two distinct views of every visit:
  1. A formal, objective **Clinical Observation** for doctors and nursing staff.
  2. A warm, accessible, plain-language **Patient Summary** for the patient.
- **Hospital Ward Management**: Provide three dedicated, real-time web portals sharing a unified database:
  - **Receptionist Dashboard** for patient intake, face enrollment, and ward bed management.
  - **Clinician Dashboard** for bedside task scheduling, queue monitoring, and clinical history review.
  - **Patient Portal** for patients to securely view their own checkup history using a unique access PIN.

---

## 2. Safety & Medical Disclaimers

> [!CAUTION]
> **Academic & Hobby Prototype Only**: ANNA is not a certified medical device and does not diagnose, treat, or offer clinical prognosis for any illness or medical condition.
> - **ECG Rhythm Analysis**: The ECG circuit employs a single-lead analog front-end (AD8232) feeding a 16-bit ADC (ADS1115). Rhythm evaluation is based on simple R-peak variance heuristics (Normal Sinus Rhythm vs. Slightly Irregular vs. Irregular) and is prone to movement artifacts.
> - **Simulated Pulse**: The current prototype hardware generates a simulated pulse value pending integration of a clinical PPG/pulse-oximeter module.
> - **AI Hallucination Guardrails**: Prompts supplied to Google Gemini enforce strict system rules preventing the LLM from diagnosing conditions or claiming guaranteed stability. Every output explicitly includes: *"Requires clinician review; prototype readings are not diagnostic."*

---

## 3. System Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                              ANNA ROBOT HARDWARE                                  |
|                                                                                   |
|  +--------------------+   +---------------------+   +--------------------------+  |
|  |   Pi Camera / USB  |   |  HC-SR04 Ultrasonic |   |  L298N Motor Controller  |  |
|  |  (V4L2 640x480)    |   |  (Distance / Safety)|   |  (Differential 2-Wheel)  |  |
|  +---------+----------+   +----------+----------+   +------------+-------------+  |
|            |                         |                           |                |
|  +---------+-------------------------+---------------------------+-------------+  |
|  |                           Raspberry Pi 4B / Compute Module                  |  |
|  |                                                                             |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  |  |                        anna_robot.robot.HealthcareRobot               |  |  |
|  |  |                               (Finite State Machine)                  |  |  |
|  |  +-------+--------------------+---------------------+--------------------+  |  |
|  |          |                    |                     |                       |  |
|  |  +-------v--------+  +--------v-----------+  +------v--------------------+  |  |
|  |  |   Perception   |  |     Sensors        |  |     Interaction           |  |  |
|  |  | - Person TFLite|  | - DS18B20 (1-Wire) |  | - pyttsx3 (TTS)           |  |  |
|  |  | - Emotion TFLite|  | - Simulated Pulse  |  | - Google Gemini API       |  |  |
|  |  | - Face Recog   |  | - ADS1115 ECG ADC  |  | - JSON Telemetry (TCP)    |  |  |
|  |  +----------------+  +--------------------+  +--------------+------------+  |  |
|  +-------------------------------------------------------------|---------------+  |
+----------------------------------------------------------------|------------------+
                                                                 | TCP :5000
                                                                 v
+-----------------------------------------------------------------------------------+
|                             HOSPITAL WEB PLATFORM                                 |
|                                                                                   |
|  +-------------------------+  +-----------------------+  +---------------------+  |
|  |  Receptionist Portal    |  |  Clinician Dashboard  |  |    Patient Portal   |  |
|  |  (Port :8001)           |  |  (Port :8002)         |  |    (Port :8003)     |  |
|  |  - Bed Map Management   |  |  - Session Auth       |  |  - PIN Authentication|  |
|  |  - Patient Admission    |  |  - Task Dispatch      |  |  - Plain Language    |  |
|  |  - OpenCV Face Validate |  |  - Clinical Summaries |  |    Health Records    |  |
|  +------------+------------+  +-----------+-----------+  +----------+----------+  |
|               |                           |                         |             |
|               +---------------------+     |     +-------------------+             |
|                                     |     |     |                                 |
|                               +-----v-----v-----v-----+                           |
|                               |   SQLAlchemy 2.0 ORM  |                           |
|                               +-----------+-----------+                           |
|                                           |                                       |
|                               +-----------v-----------+                           |
|                               |  SQLite / PostgreSQL  |                           |
|                               |  (Unified Database)   |                           |
|                               +-----------------------+                           |
+-----------------------------------------------------------------------------------+
```

---

## 4. Hardware Component Specifications & Wiring

### Hardware BOM (Bill of Materials)
1. **Host Computer**: Raspberry Pi 4B (4GB or 8GB RAM recommended) running Raspberry Pi OS (Debian-based).
2. **Camera**: Raspberry Pi Camera Module v2/v3 (CSI) or standard USB V4L2 webcam.
3. **Chassis & Drive**: 2-wheel differential drive chassis with continuous DC gearmotors.
4. **Motor Driver**: L298N Dual H-Bridge motor driver board.
5. **Distance Sensor**: HC-SR04 ultrasonic distance sensor with voltage divider for Pi Echo pin (5V to 3.3V).
6. **Temperature Probe**: DS18B20 waterproof 1-Wire temperature sensor with 4.7kΩ pull-up resistor.
7. **ECG Front-end**: AD8232 single-lead heart rate monitor board.
8. **ADC Converter**: ADS1115 16-Bit I2C ADC converter (I2C address `0x48`).
9. **Audio System**: USB speaker or 3.5mm amplified speaker jack for Text-To-Speech.

### Default GPIO Pinout Map (BCM Numbering)

| Hardware Component | Component Pin | Raspberry Pi Pin (BCM) | Physical Pin | Purpose / Function |
| :--- | :--- | :--- | :--- | :--- |
| **HC-SR04 Ultrasonic** | `TRIG` | `GPIO 23` | Pin 16 | Ultrasonic pulse trigger |
| | `ECHO` | `GPIO 24` | Pin 18 | Pulse echo return (via voltage divider) |
| **L298N Motor Driver** | `IN1` (Left Dir) | `GPIO 17` | Pin 11 | Left motor direction |
| | `ENA` (Left PWM) | `GPIO 18` | Pin 12 | Left motor speed control (PWM) |
| | `IN3` (Right Dir)| `GPIO 22` | Pin 15 | Right motor direction |
| | `ENB` (Right PWM)| `GPIO 27` | Pin 13 | Right motor speed control (PWM) |
| **AD8232 ECG** | `LO+` (Leads Off +) | `GPIO 5` | Pin 29 | Right electrode detachment detector |
| | `LO-` (Leads Off -) | `GPIO 6` | Pin 31 | Left electrode detachment detector |
| | `OUTPUT` | `ADS1115 A0` | ADC Pin A0 | Analog ECG signal |
| **ADS1115 ADC** | `SDA` | `GPIO 2` (SDA) | Pin 3 | I2C Data |
| | `SCL` | `GPIO 3` (SCL) | Pin 5 | I2C Clock |
| **DS18B20 Temp** | `DATA` | `GPIO 4` (1-Wire) | Pin 7 | Dallas 1-Wire serial bus |

---

## 5. File-by-File Technical Directory Breakdown

### Root Directory
- [`.env.example`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/.env.example): Exhaustive environment template covering database switches (`sqlite` vs `postgres`), port numbers, hospital parameters, credentials, and API keys.
- [`CMakeLists.txt`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/CMakeLists.txt): Multi-target CMake build and execution system. Defines targets:
  - `deps`: Builds `.venv` and installs dependencies.
  - `check`: Runs `compileall` syntax validation across the repository.
  - `run`: Launches the robot CLI.
  - `init-db`: Seeds beds and tables.
  - `receptionist`, `clinician`, `patient`: Starts each respective dashboard.
  - `db-up` / `db-down`: Docker Compose helpers.
- [`docker-compose.yml`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/docker-compose.yml): Spawns an official PostgreSQL 16 Alpine container with persistent health checks and volume mounts.
- [`requirements.txt`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/requirements.txt): Robot runtime packages: `opencv-python`, `numpy`, `RPi.GPIO`, `adafruit-blinka`, `adafruit-circuitpython-ads1x15`, `face_recognition`, `dlib`, `tflite-runtime`, `pyttsx3`, `google-genai`.
- [`requirements-dashboard.txt`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/requirements-dashboard.txt): Dashboard server dependencies: `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg2-binary`, `python-multipart`, `python-dotenv`, `itsdangerous`, `opencv-python-headless`.
- [`run.sh`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/run.sh): Shell script for Raspberry Pi OS. Verifies dependencies, verifies model assets, exports variables, and executes the controller.

---

### `anna_robot/` (Robot Core Package)

#### 1. [`config.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/config.py)
Declares the `@dataclass Config` object. Automatically parses environment variables or applies defaults:
- `gemini_api_key`: Google Gemini API access token.
- `gemini_model`: Defaults to `models/gemini-flash-latest`.
- `distance_trigger_cm`: `60.0 cm` (distance threshold to transition from tracking to interacting).
- `safety_stop_cm`: `20.0 cm` (absolute emergency braking threshold).
- `person_detection_threshold`: `0.65` (MobileNet confidence cutoff).
- `face_match_threshold`: `0.45` (Euclidean distance threshold for dlib encodings; lower is stricter).
- `person_confirm_frames`: `3` consecutive frames required before tracking moves motors.
- `max_unknown_attempts`: `3` attempts before giving up on an unregistered face.
- Pin assignments and TTS speeds.

#### 2. [`main.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/main.py)
CLI entrypoint. Configures Python `logging`, parses CLI flags (`--port`, `--log-level`, `--no-debug-window`), instantiates `HealthcareRobot`, and calls `robot.run()`.

#### 3. [`robot.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/robot.py)
The central controller coordinating hardware, perception, and state flow:
- **`__init__`**: Binds all peripheral classes (`MotorController`, `UltrasonicSensor`, `TemperatureSensor`, `SimulatedPulseSensor`, `EcgSensor`, `PersonDetector`, `FaceIdentifier`, `EmotionDetector`, `VoiceAssistant`, `GeminiAssistant`, and `TelemetryLink`).
- **`run`**: Main infinite control loop. Acquires camera frames, samples ultrasonic distance, emits JSON status over TCP, reads companion voice commands, and invokes the active state handler (`_step`).
- **`_handle_search`**: Runs object detection. Centers person by turning left/right or moving forward.
- **`_handle_interact`**: Extracts face bounding box, compares encoding with known database, classifies emotion, speaks Gemini greeting, and asks for voice confirmation.
- **`_handle_wait_confirm`**: Listens for `"yes buddy"` command.
- **`_handle_health_check`**: Sub-state machine driving sequential vital measurements and questionnaires.
- **`_handle_done`**: Resets patient session data and re-enters search state.
- **`shutdown`**: Safe cleanup of camera, GPIO pins, and network sockets.

#### 4. [`state.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/state.py)
Defines FSM enums and question constants:
- **`RobotState`**: `STARTUP`, `SEARCH`, `INTERACT`, `WAIT_CONFIRM`, `HEALTH_CHECK`, `DONE`.
- **`HealthStage`**: `ASK_TEMP`, `WAIT_TEMP`, `ASK_PULSE`, `WAIT_PULSE`, `ASK_ECG`, `WAIT_ECG`, `ASK_QUESTION`, `WAIT_ANSWER`.
- **`HEALTH_QUESTIONS`**: Tuple of `HealthQuestion` namedtuples covering:
  1. Sleep hours (`"How many hours of sleep did you get last night? Please say a number."`)
  2. Water intake (`"How many glasses of water have you had today? Please say a number."`)
  3. Pain & discomfort (`"Are you feeling any pain or discomfort today? Please say yes or no."`)
  4. Appetite (`"How is your appetite today? Please say good, poor, or normal."`)
  5. Physical activity (`"Did you do any physical activity or exercise today? Please say yes or no."`)
  6. Stress rating (`"On a scale of one to ten, how stressed are you feeling today? Say a number."`)

#### 5. [`patient_session.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/patient_session.py)
Encapsulates runtime patient data during a single session:
- Fields: `name`, `emotion`, `temperature`, `pulse`, `ecg`, `health_report`, `clinical_report`, `answers`.
- Methods: `reset()` to flush data between patients; `to_telemetry()` to serialize data for TCP dashboard broadcasts.

#### 6. [`gemini_assistant.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/gemini_assistant.py)
Integrates Google Generative AI via `google.genai.Client`:
- **`emotion_greeting(name, emotion)`**: Selects an emotion-tailored prompt template (e.g., empathetic for Sad, soothing for Angry, reassuring for Fear) and asks Gemini for a 2-sentence conversational greeting.
- **`health_summaries(...)`**: Ingests vitals and questionnaire answers, simultaneously generating:
  1. An objective medical observation for clinicians.
  2. A plain-language, encouraging summary for the patient.
- **Graceful Fallbacks**: If the API key is missing or internet connectivity drops, returns pre-composed static responses without stalling the robot.

#### 7. [`voice.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/voice.py)
Text-to-speech module using `pyttsx3`. Contains a specialized reliability enhancement: Linux `espeak` is prone to memory leaks and process hangs when re-invoked in a single long-running process. The `VoiceAssistant` class re-initializes the TTS engine per utterance by default, avoiding audio hangs.

#### 8. [`telemetry.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/telemetry.py)
Provides non-blocking JSON-over-TCP communications. Accepts a companion client on port `5000`. Broadcasts live telemetry packets every loop iteration (e.g. distance, robot state, current vital readings) and receives incoming voice commands.

#### 9. [`motors.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/motors.py)
Controls the dual DC motors via L298N H-Bridge using `RPi.GPIO`:
- Methods: `forward()`, `turn_left()`, `turn_right()`, `stop()`.
- Uses Hardware PWM on speed control pins to maintain balanced driving velocity.

#### 10. [`utils.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/utils.py)
Utility functions for text formatting, stripping special symbols, and ensuring safe string conversions for speech synthesis.

---

### `anna_robot/sensors/` (Sensory Interface Layer)

- [`temperature.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/sensors/temperature.py): Interacts with Linux kernel 1-Wire subsystem (`/sys/bus/w1/devices/28*/w1_slave`). Parses temperature readings with CRC validation and automatic retry logic.
- [`pulse.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/sensors/pulse.py): Generates simulated baseline heart rate readings (`70 - 80 BPM`) for pipeline validation.
- [`ecg.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/sensors/ecg.py): Samples 500 points at 100 Hz (10 ms intervals) via ADS1115 ADC over I2C. Normalizes signal, performs R-peak detection against standard deviation thresholds, computes interval standard deviation divided by mean, and classifies rhythm regularity (`Normal Sinus Rhythm`, `Slightly Irregular`, or `Irregular`).
- [`ultrasonic.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/sensors/ultrasonic.py): Emits 10 µs trigger pulse on `GPIO 23`, measures echo pulse duration on `GPIO 24`, and calculates distance in centimeters based on the speed of sound ($343\text{ m/s}$).

---

### `anna_robot/perception/` (Computer Vision & Edge AI)

- [`person_detector.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/perception/person_detector.py): Executes TFLite MobileNet SSD model (`models/person_detect.tflite`). Resizes frame, executes inference, filters for Class ID 0 (`person`), and returns bounding box coordinates.
- [`face_identifier.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/perception/face_identifier.py): Scans the `known_faces/` folder on startup. Uses `dlib` 68-point facial landmark detector to compute 128-dimensional facial embeddings. Performs Euclidean distance comparisons against live camera frames to identify patients.
- [`emotion_detector.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/anna_robot/perception/emotion_detector.py): Uses a lightweight neural network (`models/emotion_model.tflite`). Takes cropped face bounding boxes, converts to single-channel grayscale, and classifies facial expression into one of 7 emotion categories.

---

### `dashboards/` (Web Platform)

#### Common Layer (`dashboards/common/`)
- [`database.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/common/database.py): Initializes SQLAlchemy `create_engine`, scoped session maker `SessionLocal`, and declarative base `Base`. Automatically switches between SQLite and PostgreSQL based on configuration.
- [`models.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/common/models.py): Defines four relational database entities:
  - `Bed`: `bed_number` (PK), `is_occupied` (Boolean).
  - `Patient`: `id`, `patient_code` (Unique Index, e.g. `ANP-00001`), `full_name`, `blood_group`, `height_cm`, `weight_kg`, `photo_path`, `bed_number` (FK to beds), `registered_at`, `discharged_at`, `portal_pin`.
  - `RobotTask`: `id`, `patient_id` (FK), `task_type`, `instructions`, `priority` (`normal` / `urgent`), `status` (`queued`, `in_progress`, `completed`, `failed`), `assigned_by`, timestamps.
  - `MedicalSummary`: `id`, `patient_id` (FK), `task_id` (FK), `author`, `summary` (Doctor view), `patient_summary` (Patient view), `temperature_c`, `pulse_bpm`, `ecg_note`, `created_at`.
- [`config.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/common/config.py): Dashboard settings reading database configurations, auth tokens, and session secrets.
- [`init_db.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/init_db.py): Creates database tables and seeds the bed pool (defaults to 20 beds). Safe to run repeatedly (idempotent).

---

#### 1. Receptionist Dashboard (`dashboards/receptionist/`)
- **Port**: `8001`
- **Purpose**: Patient intake and bed allocation.
- **Key Modules**:
  - [`face_check.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/receptionist/face_check.py): Verifies uploaded patient photographs using OpenCV Haar Cascades (frontal default, frontal alt2, and mirrored profile cascade). Checks that **exactly 1 face** is present before saving.
  - [`crud.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/receptionist/crud.py): Encapsulates admission, photo saving into `known_faces/`, bed locking, and discharge workflows.
  - [`main.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/receptionist/main.py): Exposes REST endpoints:
    - `GET /api/beds`: List all beds and occupant statuses.
    - `POST /api/photo-check`: Real-time instant validation of photos.
    - `POST /api/patients`: Registers patient, assigns bed, and writes photo to `known_faces/`.
    - `POST /api/beds/{bed_number}/discharge`: Discharges patient and frees bed.

---

#### 2. Clinician Dashboard (`dashboards/clinician/`)
- **Port**: `8002`
- **Purpose**: Task assignment, visit queue management, clinical report inspection, and telepresence preview.
- **Key Modules**:
  - [`main.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/clinician/main.py):
    - Session-based authentication (`POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`).
    - `GET /api/patients`: Search active or past patients.
    - `POST /api/patients/{code}/portal-pin`: Generates/resets patient 6-digit access PIN.
    - `GET /api/tasks` & `POST /api/tasks`: Queue prioritized bedside tasks for the robot.
    - `POST /api/robot/tasks/next`: Protected endpoint (`X-Anna-Robot-Key`) for robot to claim next queued task.
    - `POST /api/robot/tasks/{id}/complete`: Endpoint for robot to report visit summary, sensor readings, and completion.

---

#### 3. Patient Portal (`dashboards/patient/`)
- **Port**: `8003`
- **Purpose**: Confidential patient access to personal health summaries.
- **Key Modules**:
  - [`main.py`](file:///c:/Users/suraj_5xz7ats/OneDrive/Desktop/Healthcare%20bot/ANNA/dashboards/patient/main.py):
    - Authenticates using `patient_code` and `portal_pin`.
    - `GET /api/profile`: Displays patient details.
    - `GET /api/history`: Displays chronological list of visit summaries written specifically in patient-friendly language.

---

## 6. Environment Variables Reference

| Variable Name | Default Value | Description / Usage |
| :--- | :--- | :--- |
| `DB_ENGINE` | `sqlite` | Database selector: `sqlite` or `postgres` |
| `SQLITE_PATH` | `anna_dashboard.db` | File path for SQLite database file |
| `POSTGRES_HOST` | `localhost` | PostgreSQL hostname |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `anna_hospital` | PostgreSQL database name |
| `POSTGRES_USER` | `anna` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `anna_dev_password` | PostgreSQL password |
| `HOSPITAL_TOTAL_BEDS` | `20` | Number of beds seeded into the ward map |
| `PATIENT_ID_PREFIX` | `ANP` | Prefix for generated patient codes (e.g. `ANP-00001`) |
| `RECEPTIONIST_PORT` | `8001` | HTTP port for Receptionist app |
| `CLINICIAN_PORT` | `8002` | HTTP port for Clinician app |
| `PATIENT_PORT` | `8003` | HTTP port for Patient portal |
| `CLINICIAN_EMAIL` | `doctor@anna.local` | Doctor/nurse sign-in identity |
| `CLINICIAN_PASSWORD` | `change-me` | Doctor/nurse sign-in password |
| `DASHBOARD_SESSION_SECRET`| *(Random string)* | Cryptographic key for cookie sessions |
| `ROBOT_API_KEY` | `change-robot-key` | Shared secret authorizing robot HTTP requests |
| `GEMINI_API_KEY` | *(None)* | Google Cloud API key for Gemini LLM features |
| `GEMINI_MODEL` | `models/gemini-flash-latest` | Model identifier for Gemini API |
| `ROBOT_TCP_PORT` | `5000` | Port for robot JSON telemetry socket |
| `ROBOT_DISTANCE_TRIGGER_CM`| `60.0` | Approaching distance cutoff before starting greeting |
| `ROBOT_SAFETY_STOP_CM` | `20.0` | Emergency obstacle stop distance |
| `ROBOT_PERSON_THRESHOLD` | `0.65` | Confidence threshold for Person detector |
| `ROBOT_FACE_MATCH_THRESHOLD` | `0.45` | Face matching Euclidean distance threshold |
| `ROBOT_PERSON_MODEL` | `models/person_detect.tflite` | Path to person detection TFLite model |
| `ROBOT_EMOTION_MODEL` | `models/emotion_model.tflite` | Path to emotion classification TFLite model |
| `ROBOT_KNOWN_FACES_DIR` | `known_faces` | Root directory for stored face photos |
| `ROBOT_SHOW_DEBUG_WINDOW` | `true` | Show local OpenCV preview window |

---

## 7. Operational Workflow (End-to-End Walkthrough)

1. **Patient Admission**:
   - The receptionist opens **http://localhost:8001**.
   - They click an empty bed on the ward map, enter the patient's vitals (Name, Height, Weight, Blood Group), and capture a photo.
   - OpenCV verifies the photo has 1 face, saves it to `known_faces/<Full Name>/reference.jpg`, marks the bed occupied, and generates patient code `ANP-00001` with a 6-digit portal PIN.
2. **Task Assignment**:
   - A clinician logs into **http://localhost:8002**.
   - The doctor selects `ANP-00001` and clicks **Assign Visit** (priority: normal or urgent).
   - The task enters the database queue as `queued`.
3. **Robot Search & Engagement**:
   - The robot navigates the ward in `SEARCH` mode using its camera and ultrasonic sensor.
   - It detects a human with `person_detect.tflite` and approaches to $60\text{ cm}$.
   - It captures the face, identifies the patient using `face_recognition`, and predicts their emotion (e.g. `Happy`).
   - The robot calls Gemini to synthesize a personalized greeting: *"Hello Alice, you look in great spirits today! Whenever you are ready, say 'yes buddy' to begin your checkup."*
4. **Health Check Execution**:
   - The patient confirms with *"yes buddy"*.
   - The robot walks the patient through Temperature, Pulse, and ECG measurements, followed by 6 wellness questions.
5. **Dual Report Generation**:
   - Gemini compiles the collected vitals and answers into both a clinician report and a patient report.
   - The robot transmits the record via `POST /api/robot/tasks/{id}/complete` to the clinician dashboard and verbally reassures the patient.
6. **Review**:
   - The doctor inspects the clinical record on the Clinician Dashboard.
   - The patient signs into **http://localhost:8003** with their PIN to review their visit report in plain language.
