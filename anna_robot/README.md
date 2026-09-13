# 🤖 Anna Robot Core

The core logic for the ANNA Healthcare Assistant Robot, including perception, motor control, and the state machine.

## 🛠️ Implementation Details

### 1. Local Voice Interaction
To ensure the robot can operate reliably without depending on a companion device for listening, it implements a fully local voice pipeline:
- **Speech-to-Text (STT)**: Uses `Vosk` for offline, real-time speech recognition. It listens via a background thread and identifies keywords like *"yes buddy"* or *"check temperature"*.
- **Text-to-Speech (TTS)**: Uses `Piper`, a fast, local neural TTS system that provides high-quality, natural voices.

### 2. Perception Pipeline
- **Person Detection**: TFLite SSD MobileNet model for finding people.
- **Face Identification**: `face_recognition` (dlib) for matching faces against the `known_faces/` directory.
- **Emotion Detection**: TFLite model to detect patient mood for empathetic greetings.

### 3. State Machine
The robot operates as a state machine (`RobotState`):
- `SEARCH` $\rightarrow$ `INTERACT` $\rightarrow$ `WAIT_CONFIRM` $\rightarrow$ `HEALTH_CHECK` $\rightarrow$ `DONE`.
- **Command Priority**: The robot prioritizes **Local Voice Input** over Network/Telemetry commands to ensure the patient always has immediate control.

### 4. Telemetry
A JSON-over-TCP link allows a companion PC to:
- Monitor robot status (distance, state, current patient).
- Send high-level commands (e.g., "navigate to patient X").

## 🚀 Running the Robot
The simplest way to start is using the root `run.sh` script:
```bash
./run.sh
```
This script handles the virtual environment creation, dependency installation, and launches `anna_robot.main`.
