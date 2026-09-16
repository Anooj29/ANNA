# Anna - Healthcare Assistant Robot

A Raspberry Pi robot that finds a person, recognises them by face, and walks
them through a short guided health check (temperature, pulse, ECG, and a
few spoken questions), then gives a friendly Gemini-generated wellness
summary. Status is streamed to a companion laptop/dashboard over TCP.

ANNA answers to **"Hey ANNA"** and **"Yes ANNA"**, follows a person on
request under PID control, keeps them centred in frame with a two-servo
head, and recognises the furniture around her as well as people.

## What ANNA can do

| Capability | Where it lives |
|---|---|
| Find, approach and greet a registered patient | `robot.py`, `perception/` |
| Guided health check + Gemini wellness summary | `robot.py`, `gemini_assistant.py` |
| **PID control on visual feedback** | `control/pid.py`, `control/visual.py` |
| **Smooth person following** | `control/follower.py` |
| **Multi-class object detection** (person, chair, couch, bed, dining table, tv) | `perception/object_detector.py` |
| **"Hey ANNA" / "Yes ANNA" wake words and intents** | `interaction/` |
| **Two-servo head that keeps a person centred, within hard limits** | `head_tracker.py` |
| Wheel-encoder feedback *(implemented, off until encoders are fitted)* | `control/encoder.py` |
| IMU feedback *(implemented, off until an IMU is fitted)* | `control/imu.py` |
| Live annotated camera stream for clinicians | `vision_stream.py` |

Run `pytest` to exercise all of it with no hardware attached.

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
- *Optional:* two hobby servos for the pan/tilt head (see
  [The head](#the-head-person-tracking-with-two-servos))
- *Optional:* a USB microphone, for hearing "Hey ANNA" in the room rather
  than via the companion app
- *Planned:* wheel encoders and an IMU - the software segments for both are
  already written and switched off

Default GPIO pin assignments (BCM numbering) live in `anna_robot/config.py`
and can be overridden with environment variables - see below.

## Project layout

```
├── CMakeLists.txt        # optional build/run/install/test wrapper (see below)
├── requirements.txt      # robot dependencies
├── requirements-dev.txt  # test dependencies (no hardware needed)
├── requirements-optional.txt  # microphone extras
├── run.sh                # one-command launcher (venv + pip install + run)
├── models/               # put person_detect.tflite + emotion_model.tflite here
├── known_faces/          # one sub-folder of reference photos per patient
├── tests/                # pytest suite - runs anywhere, no Pi required
└── anna_robot/           # the Python package
    ├── main.py             # CLI entry point
    ├── robot.py            # the state machine that ties everything together
    ├── config.py           # environment-driven configuration + validation
    ├── state.py            # RobotState / HealthStage enums + questionnaire
    ├── patient_session.py  # per-patient session data
    ├── gemini_assistant.py # Gemini greetings + summaries (non-blocking)
    ├── voice.py            # queued, non-blocking text-to-speech
    ├── telemetry.py        # JSON-over-TCP link to a companion device
    ├── motors.py           # differential-drive mixing + ramped commands
    ├── head_tracker.py     # two-servo head that keeps a person centred
    ├── overlay.py          # the annotations drawn for staff
    ├── vision_stream.py    # MJPEG stream of the annotated camera
    ├── utils.py            # shared scalar maths (clamp, slew, filters...)
    ├── hardware/           # GPIO / camera / servo access
    │   ├── gpio.py           # RPi.GPIO, or a simulated backend off-Pi
    │   ├── camera.py         # threaded capture; always the newest frame
    │   └── servo.py          # servo driver that enforces travel limits
    ├── control/           # feedback control
    │   ├── pid.py            # the one shared PID implementation
    │   ├── feedback.py       # the contract every feedback source implements
    │   ├── visual.py         # camera feedback  (ACTIVE)
    │   ├── encoder.py        # wheel-encoder odometry (future hardware)
    │   ├── imu.py            # IMU heading/yaw rate (future hardware)
    │   └── follower.py       # smooth person following
    ├── interaction/       # speech and human interaction
    │   ├── wake_word.py      # "Hey ANNA" / "Yes ANNA" + intent parsing
    │   ├── dialogue.py       # what ANNA says
    │   └── listener.py       # optional on-board microphone
    ├── sensors/           # ultrasonic, temperature, pulse, ECG
    └── perception/        # object detection, tracking, face ID, emotion
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

## Talking to ANNA

ANNA listens for a wake word and then acts on what follows. Both of these
work, and the wake word can be in the same sentence as the command:

```
"Hey ANNA"                      -> "Yes? I am listening."
"Hey ANNA, start my health check"
"Yes ANNA, follow me"
```

After a wake word she stays attentive for 12 seconds
(`ROBOT_WAKE_WINDOW_S`), so a follow-up sentence does not need her name
again. **"Stop"** is always heard, wake word or not, and keeps her still for
`ROBOT_STOP_HOLD_S` seconds afterwards - otherwise the next control tick
would see the same person and drive off again. Any explicit movement command
("follow me") clears the hold immediately.

Recognised commands (any reasonable phrasing works - matching is tolerant of
filler words and of the recogniser mishearing her name):

| Say | ANNA does |
|---|---|
| "hey ANNA" / "yes ANNA" | Acknowledges and starts listening |
| "start my health check" *(or the original "yes buddy")* | Begins the guided check |
| "check temperature" / "check pulse" / "check ecg" | Takes that reading |
| "follow me" | Follows you at a comfortable distance |
| "stop following" / "wait here" | Stops and waits |
| "stop" | Stops immediately, from any state |
| "what do you see" | Lists the people and furniture in view |
| "who am I" | Says who she has recognised |
| "what can you do" | Describes her capabilities |
| "say that again" | Repeats her last line |

Speech can reach ANNA two ways, and both feed the same command handling:
the companion app over TCP (the default, unchanged), and - if you enable it
with `ROBOT_MIC_ENABLED=true` - a microphone on the Pi itself. The
microphone needs `pip install -r requirements-optional.txt`; without it
ANNA logs one clear message and carries on using the companion link.

## Following a person

Say "follow me" and ANNA holds station roughly 90 cm behind you
(`ROBOT_FOLLOW_DISTANCE_CM`). The motion is deliberately smooth rather than
reactive:

- Two PID loops: **bearing** drives yaw, **range** drives forward speed.
- Both run on a *smoothed* target, so one jittery detection does not reach
  the wheels.
- Forward speed tapers off while turning hard, so she arcs into line rather
  than swinging around you.
- Arrival uses hysteresis: she stops on reaching the comfort band and only
  sets off again once you are clearly further away, which is what stops the
  usual creeping back and forth.
- Losing sight of you coasts to a stop first, then sweeps toward the side
  you were last seen on, and finally gives up and waits.
- The ultrasonic sensor has the final word: anything inside
  `ROBOT_SAFETY_STOP_CM` cuts forward motion regardless of what the PIDs want.

Tune it with `ROBOT_BEARING_KP/KI/KD` and `ROBOT_RANGE_KP/KI/KD`. Each loop's
live error, P/I/D terms and saturation flag are published in the telemetry
packet under `pid`, so you can tune against real numbers rather than guesses.

## Feedback segments (vision now, encoders and IMU later)

Every feedback modality implements the same small contract
(`control/feedback.py`) and registers with a bus that selects the most
trustworthy fresh estimate:

| Segment | State | What it contributes |
|---|---|---|
| `control/visual.py` | **Active** | Target bearing and range from the camera |
| `control/encoder.py` | Implemented, **off** | Wheel odometry: distance travelled and heading, including through a detection dropout |
| `control/imu.py` | Implemented, **off** | Yaw rate and heading at a far higher rate than the camera, including wheel slip |

The encoder and IMU segments are complete - quadrature counting, tick-to-metre
conversion, differential-drive odometry, gyro bias calibration and all - and
disabled by default because the hardware is not fitted yet. Turning them on
is a configuration change, not a refactor:

```bash
ROBOT_ENCODER_ENABLED=true ROBOT_ENCODER_LEFT_PIN=20 ROBOT_ENCODER_RIGHT_PIN=21
ROBOT_IMU_ENABLED=true      # plus an ImuReader implementation for your chip
```

## The head: person tracking with two servos

`anna_robot/head_tracker.py` drives a pan servo and a tilt servo to keep the
person in the middle of the frame while the body does something else. It
runs its own PID per axis, with a deadband so a centred person does not make
the head hunt, and slew-rate limiting so motion is smooth rather than snappy.
When nothing has been seen for a few seconds the head drifts back to centre
and the servos are released, which stops them buzzing and heating.

### The travel limits, and why they are not optional

**The head carries the camera cable. It must never be able to rotate freely -
a full turn would wind and eventually tear the loom.** The limits are
enforced in three independent places, so no single mistake can defeat them:

1. `ServoLimits` validates the configured range at construction and rejects
   anything outside ±90°.
2. `Servo` clamps every commanded angle *and* every value written to the PWM
   pin.
3. `HeadTracker` clamps its own PID output and stops integrating once an
   axis reaches a limit, so the controller cannot wind up against the stop.

`Config.validate()` refuses to start the robot at all if the configured
travel is out of range, and `tests/test_head_tracker.py` holds the property
down from each of those directions.

Defaults are conservative: **±70° pan, ±30° tilt**. Measure the real cable
slack on your machine before widening them. When the head reaches a limit it
says so in the overlay and telemetry, and the body turn takes over.

Wire the servos to any two free GPIO pins and tell ANNA which:

```bash
ROBOT_HEAD_PAN_PIN=12 ROBOT_HEAD_TILT_PIN=13 ./run.sh
# or: ./run.sh --head-pan-pin 12 --head-tilt-pin 13
```

With no pins configured, head tracking simply stays off and everything else
works as before.

## Objects ANNA recognises

One detection model serves everything, so the extra classes cost no extra
frame time. By default she reports **person, chair, couch, bed, dining
table and tv** - person is what drives behaviour, and the furniture gives
staff (and "what do you see?") useful context. Change the list with:

```bash
ROBOT_DETECTION_CLASSES="person,chair,bed,couch,tv"
```

Keep it short. Every extra class is more boxes to draw, annotate and stream.

## Running the tests

The suite needs no Raspberry Pi, no camera, no models and no network - GPIO
is simulated and the camera and models are faked:

```bash
pip install -r requirements-dev.txt
pytest
```

There is also a dry-run mode that starts the real control stack with every
actuator simulated, which is the quickest way to check behaviour changes on
a desk:

```bash
./run.sh --simulate --no-wait --no-debug-window
```

And a settings check that validates everything without energising anything:

```bash
python3 -m anna_robot.main --check-config
```

## Configuration

Everything is overridable via environment variables. Invalid values log a
warning and fall back to the default rather than crashing; genuinely unsafe
combinations (a stop distance beyond the follow distance, head travel past
±90°, two devices on one GPIO pin) are refused at startup.

### Assistant and companion link

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | *(none)* | Gemini API key; falls back to canned text if unset |
| `GEMINI_MODEL` | `models/gemini-flash-latest` | Gemini model name |
| `ROBOT_GEMINI_TIMEOUT_S` | `12.0` | Timeout for a background Gemini request |
| `ROBOT_TCP_PORT` | `5000` | Telemetry TCP port |
| `ROBOT_TCP_WAIT_FOR_CLIENT` | `true` | Wait at startup for a companion to connect |
| `ROBOT_TCP_CONNECT_TIMEOUT_S` | *(none)* | Give up waiting after this many seconds |

### Behaviour

| Variable | Default | Meaning |
|---|---|---|
| `ROBOT_DISTANCE_TRIGGER_CM` | `60.0` | Distance at which the robot stops and greets |
| `ROBOT_SAFETY_STOP_CM` | `20.0` | Hard stop distance; forward motion is cut inside it |
| `ROBOT_PERSON_THRESHOLD` | `0.65` | Detection confidence threshold |
| `ROBOT_FACE_MATCH_THRESHOLD` | `0.45` | Face-match distance threshold (lower = stricter) |
| `ROBOT_PERSON_CONFIRM_FRAMES` | `3` | Sightings needed to confirm a person |
| `ROBOT_MAX_UNKNOWN_ATTEMPTS` | `3` | Unknown-face attempts before giving up |
| `ROBOT_MAX_NO_FACE_FRAMES` | `150` | Frames with no face before returning to search |
| `ROBOT_DONE_PAUSE_S` | `10.0` | Pause after a session before searching again |
| `ROBOT_STOP_HOLD_S` | `5.0` | How long "stop" keeps the robot still before it may drive again |

### Perception

| Variable | Default | Meaning |
|---|---|---|
| `ROBOT_PERSON_MODEL` | `models/person_detect.tflite` | Detection model path |
| `ROBOT_EMOTION_MODEL` | `models/emotion_model.tflite` | Emotion model path |
| `ROBOT_LABEL_MAP` | *(built-in COCO)* | Optional label file for the detection model |
| `ROBOT_DETECTION_CLASSES` | `person,chair,couch,bed,dining table,tv` | Classes to report |
| `ROBOT_KNOWN_FACES_DIR` | `known_faces` | Reference-photo directory |
| `ROBOT_DETECT_EVERY_N_FRAMES` | `2` | Run detection every N frames (tracking fills the gaps) |
| `ROBOT_FACE_CHECK_INTERVAL_S` | `0.4` | Minimum gap between face-recognition passes |
| `ROBOT_FACE_DETECTION_SCALE` | `0.5` | Downscale factor for face detection (lower = faster) |
| `ROBOT_INFERENCE_THREADS` | `2` | TFLite interpreter threads |

### Speech and interaction

| Variable | Default | Meaning |
|---|---|---|
| `ROBOT_TTS_RATE` | `145` | Speech rate (words/min) |
| `ROBOT_TTS_VOLUME` | `1.0` | Speech volume, 0..1 |
| `ROBOT_TTS_VOICE` | *(system default)* | pyttsx3 voice id |
| `ROBOT_TTS_REINIT_EACH_CALL` | `true` | Recreate the TTS engine per utterance (avoids a known espeak hang) |
| `ROBOT_WAKE_WINDOW_S` | `12.0` | How long ANNA stays attentive after a wake word |
| `ROBOT_REQUIRE_WAKE_WORD` | `false` | Require a wake word for every command ("stop" always works) |
| `ROBOT_MIC_ENABLED` | `false` | Listen on a local microphone as well as the companion link |
| `ROBOT_MIC_DEVICE_INDEX` | *(default device)* | Which input device to use |
| `ROBOT_MIC_DEVICE_NAME` | *(auto: camera/USB mic)* | Pick the input device by name |
| `ROBOT_MIC_SAMPLE_RATE` | *(device default)* | Force a rate such as `48000` if the mic rejects the default |
| `ROBOT_MIC_LANGUAGE` | `en-US` | Recognition language |

### Camera and vision output

| Variable | Default | Meaning |
|---|---|---|
| `ROBOT_CAMERA_INDICES` | `0,1` | Camera indices to try, in order |
| `ROBOT_CAMERA_WIDTH` / `_HEIGHT` | `640` / `480` | Capture resolution |
| `ROBOT_CAMERA_FPS` | `30` | Requested capture rate |
| `ROBOT_CAMERA_MJPG` | `true` | Request MJPG (much faster than YUYV over USB) |
| `ROBOT_CONTROL_LOOP_FPS` | `20.0` | Target control-loop rate (0 = unthrottled) |
| `ROBOT_SHOW_DEBUG_WINDOW` | `true` | Show the OpenCV preview window |
| `ROBOT_VISION_STREAM_ENABLED` | `true` | Publish the annotated camera as MJPEG |
| `ROBOT_VISION_STREAM_HOST` | `0.0.0.0` | Stream bind address |
| `ROBOT_VISION_STREAM_PORT` | `8080` | Stream port |
| `ROBOT_VISION_STREAM_TOKEN` | *(none)* | Token required to consume the stream |
| `ROBOT_VISION_STREAM_FPS` | `15.0` | Cap on stream encoding rate |
| `ROBOT_VISION_STREAM_QUALITY` | `80` | JPEG quality |

### Following and drive base

| Variable | Default | Meaning |
|---|---|---|
| `ROBOT_FOLLOW_DISTANCE_CM` | `90.0` | Distance held while following |
| `ROBOT_FOLLOW_HOLD_BAND_CM` | `18.0` | Half-width of the "close enough" band |
| `ROBOT_FOLLOW_MAX_LINEAR` | `0.5` | Forward speed ceiling, 0..1 |
| `ROBOT_FOLLOW_MAX_ANGULAR` | `0.65` | Yaw rate ceiling, 0..1 |
| `ROBOT_FOLLOW_SEARCH_TIMEOUT_S` | `8.0` | How long to search before giving up |
| `ROBOT_BEARING_KP/KI/KD` | `0.85` / `0.05` / `0.12` | Bearing (yaw) PID gains |
| `ROBOT_RANGE_KP/KI/KD` | `1.30` / `0.10` / `0.15` | Range (forward speed) PID gains |
| `ROBOT_MOTOR_MIN_DUTY` | `22.0` | Duty below which the wheels only buzz |
| `ROBOT_MOTOR_MAX_DUTY` | `55.0` | Duty ceiling |
| `ROBOT_MOTOR_RAMP_DUTY_PER_S` | `60.0` | Acceleration limit (lower = gentler) |
| `ROBOT_MOTOR_ALLOW_REVERSE` | `false` | Only enable if your driver is wired for reverse |

### Head servos

| Variable | Default | Meaning |
|---|---|---|
| `ROBOT_HEAD_ENABLED` | `true` | Enable head tracking (needs both pins below) |
| `ROBOT_HEAD_PAN_PIN` / `ROBOT_HEAD_TILT_PIN` | *(none)* | BCM pins for the two servos |
| `ROBOT_HEAD_PAN_MIN_DEG` / `_MAX_DEG` | `-70` / `70` | **Pan travel limit - protects the cabling** |
| `ROBOT_HEAD_TILT_MIN_DEG` / `_MAX_DEG` | `-30` / `30` | **Tilt travel limit** |
| `ROBOT_HEAD_PAN_SPEED_DEG_S` | `120.0` | Maximum pan speed |
| `ROBOT_HEAD_TILT_SPEED_DEG_S` | `90.0` | Maximum tilt speed |
| `ROBOT_HEAD_INVERT_PAN` / `_INVERT_TILT` | `false` | Flip a mirrored servo |
| `ROBOT_HEAD_RECENTER_AFTER_S` | `3.0` | Idle time before the head returns to centre |

### Future feedback hardware

| Variable | Default | Meaning |
|---|---|---|
| `ROBOT_ENCODER_ENABLED` | `false` | Enable wheel-encoder odometry |
| `ROBOT_ENCODER_LEFT_PIN` / `_RIGHT_PIN` | *(none)* | Encoder input pins |
| `ROBOT_ENCODER_TICKS_PER_REV` | `20` | Ticks per wheel revolution |
| `ROBOT_WHEEL_DIAMETER_M` | `0.065` | Wheel diameter |
| `ROBOT_WHEEL_BASE_M` | `0.20` | Track width between wheels |
| `ROBOT_IMU_ENABLED` | `false` | Enable IMU heading feedback |

### GPIO pin map (BCM) and runtime

| Variable | Default | Meaning |
|---|---|---|
| `ROBOT_TRIG_PIN` / `ROBOT_ECHO_PIN` | `23` / `24` | Ultrasonic sensor |
| `ROBOT_LEFT_DIR_PIN` / `ROBOT_LEFT_PWM_PIN` | `17` / `18` | Left motor |
| `ROBOT_RIGHT_DIR_PIN` / `ROBOT_RIGHT_PWM_PIN` | `22` / `27` | Right motor |
| `ROBOT_ECG_LO_PLUS_PIN` / `ROBOT_ECG_LO_MINUS_PIN` | `5` / `6` | ECG lead-off detect |
| `ROBOT_SIMULATE_HARDWARE` | `false` | Dry run: nothing physically moves |
| `ROBOT_LOG_LEVEL` | `INFO` | Logging verbosity |

CLI flags (`--port`, `--log-level`, `--no-debug-window`, `--no-wait`,
`--simulate`, `--head-pan-pin`, `--head-tilt-pin`, `--check-config`) take
priority over the environment variables above.

## Dashboards

The project provides four dashboards sharing one Postgres database:

1. **Receptionist** (built) - registers a patient (name, height, weight,
   blood group, a reference photo), assigns them a unique patient ID and a
   bed, saves the photo into `known_faces/` so ANNA can recognise them, and
   discharges patients to free their bed for reuse. Click any free bed on
   the ward map to assign it during intake; click any occupied bed to see
   who's in it and discharge them.
2. **Clinician** (built) - authenticated doctor/nurse workspace for placing
   ordered bedside visits, monitoring the queue, reviewing ANNA-generated
   visit summaries, and starting a telepresence camera preview.
3. **Patient** (built) - private portal for a patient to view their own
   friendly ANNA visit history.
4. **Robot Vision** (built) - a clinician-authenticated, read-only window
   into ANNA's live camera, including the detection overlays ANNA uses.

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

### Running dashboard 2 — clinician command

Before starting it, set `CLINICIAN_EMAIL`, `CLINICIAN_PASSWORD`,
`DASHBOARD_SESSION_SECRET`, and `ROBOT_API_KEY` to unique values in `.env`.
The clinician app uses a signed browser session; patient records, summaries,
and task assignment endpoints return `401` until a clinician signs in.

```powershell
cmake --build . --target clinician
```

Open **http://localhost:8002**. It shares the same SQLite/Postgres database
as Reception, so newly admitted patients appear automatically. Assignments
are stored in FIFO order (urgent visits are selected first). The robot-side
controller can claim the next job with `POST /api/robot/tasks/next`, using
an `X-Anna-Robot-Key` header, and complete it with
`POST /api/robot/tasks/{task_id}/complete`. A successful completion writes a
timestamped medical summary, sensor values, and ECG note to the protected
clinical record, then returns `return_to_home: true` as the controller's
instruction to perform its configured home-position routine.

The current robot prototype does not yet contain map/localisation or a
hardware-specific home-position routine. Those must be calibrated to the
actual ward, motor encoders, and safety sensors before enabling unattended
bed navigation. The dashboard/API safely provides the visit sequencing and
record workflow; connect its robot endpoints only after that physical
navigation layer has been validated. The camera panel is a local preview,
not a deployed video-conferencing service; connect it to the hospital's
approved, encrypted telehealth provider before any patient use.

### Running dashboard 3 — patient portal

```powershell
cmake --build . --target patient
```

Open **http://localhost:8003**. Patients sign in using their patient ID and
the private six-digit access PIN issued at reception (or re-issued by a
signed-in clinician through Patient Record Search). An ID alone is not a
password. The portal only exposes the signed-in patient's friendly ANNA
summaries and recorded visit values; clinician-facing observations remain
within the clinician dashboard.

### Running dashboard 4 — robot vision

ANNA publishes the annotated camera frame as an MJPEG stream on port 8080 by
default. Set `ROBOT_VISION_STREAM_URL` on the dashboard machine to the
Raspberry Pi address (for example `http://anna-robot.local:8080/stream.mjpg`)
and give both machines the same `ROBOT_VISION_STREAM_TOKEN`. Then run:

```powershell
cmake --build . --target vision
```

Open **http://localhost:8004** and sign in with the clinician credentials.
This page is deliberately view-only: it cannot move the robot, control the
camera, or send ANNA commands. It proxies the feed so the browser does not
receive the Pi address or camera token. Green overlays show people; amber
overlays show faces and recognition status.

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

The robot listens on `ROBOT_TCP_PORT`, waits for one companion client
(set `ROBOT_TCP_WAIT_FOR_CLIENT=false` or pass `--no-wait` to start without
one), then streams a newline-delimited JSON status packet every control-loop
iteration and reads back any voice-command text the companion app forwards
(e.g. "hey ANNA", "yes buddy", "check temperature", question answers).

The link now frames its input on newlines, so several commands arriving in
one TCP segment are handled as separate commands and one split across two
segments is reassembled. A companion that sends bare text with no newline -
as the original app did - still works unchanged. Disconnects are detected
and a new companion can connect at any time without restarting the robot.

Every field the original packet carried is still present. These are added
alongside them:

| Field | Contents |
|---|---|
| `fps`, `camera_fps` | Control-loop and capture rates |
| `detections` | Every object in view: label, score, box |
| `target` | The tracked person: bearing, range, confidence |
| `drive` | Commanded linear/angular velocity and following state |
| `head` | Pan/tilt angles, their limits, and whether an axis is at a stop |
| `pid` | Live error and P/I/D terms for the bearing and range loops |
| `feedback` | Each feedback segment's latest estimate and confidence |
| `listening`, `speaking` | Whether ANNA is attentive / mid-sentence |
| `health_stage` | Where the guided check has got to |

## Performance notes

The control loop does no blocking work, which is what keeps ANNA responsive
while she is talking, thinking or measuring:

| Work | How it is kept off the loop |
|---|---|
| Camera capture | A capture thread drains the driver buffer and keeps only the newest frame, so a slow iteration adds no permanent latency |
| Distance sensing | A sampling thread publishes a median-filtered reading; reading it is instant instead of costing up to 60 ms of blocking |
| Speech | Queued to a worker thread; `speak()` returns in microseconds |
| Gemini | Requested in the background and collected when ready |
| Object detection | Runs every N frames; the tracker carries the target across the gaps |
| Face recognition | Throttled, and run on a downscaled frame |
| MJPEG streaming | Skipped entirely when nobody is watching, and rate-limited when somebody is |
| The pause between patients | A deadline the loop checks, not a `sleep` |

If ANNA still feels slow, the highest-value knobs are
`ROBOT_DETECT_EVERY_N_FRAMES`, `ROBOT_FACE_DETECTION_SCALE`,
`ROBOT_CAMERA_WIDTH`/`_HEIGHT` and `ROBOT_INFERENCE_THREADS`.
