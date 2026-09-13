#!/usr/bin/env bash
# Convenience launcher for the healthcare robot.
#
# Usage:
#   ./run.sh                      # normal run
#   ./run.sh --no-debug-window    # headless run (no cv2 preview window)
#   ./run.sh --no-wait            # do not wait for the companion app
#   ./run.sh --simulate           # dry run: no motors/servos move
#   ./run.sh --check-config       # print and validate settings, then exit
#   SKIP_INSTALL=1 ./run.sh       # skip the pip install step (faster restarts)
#
# Any extra arguments are forwarded to `python3 -m anna_robot.main`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"

if [ ! -d "$VENV_DIR" ]; then
    echo "[run.sh] Creating virtual environment in $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ "${SKIP_INSTALL:-0}" != "1" ]; then
    if ! command -v cmake >/dev/null 2>&1; then
        echo "[run.sh] WARNING: 'cmake' was not found on PATH. It is required to build dlib"
        echo "          (a face_recognition dependency). Install it first, e.g.:"
        echo "          sudo apt install -y cmake build-essential"
    fi
    echo "[run.sh] Installing/updating dependencies (set SKIP_INSTALL=1 to skip)..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt
fi

if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "[run.sh] WARNING: GEMINI_API_KEY is not set. Gemini greetings/summaries will fall back to canned text."
fi

for dir in models known_faces; do
    if [ ! -d "$dir" ]; then
        echo "[run.sh] Creating missing '$dir/' directory."
        mkdir -p "$dir"
    fi
done

if [ ! -f "models/person_detect.tflite" ] || [ ! -f "models/emotion_model.tflite" ]; then
    echo "[run.sh] WARNING: expected TFLite models not found in models/ (person_detect.tflite, emotion_model.tflite)."
    echo "          See models/README.md for which files to download."
fi

# Catch bad settings before anything is energised.
if ! python3 -m anna_robot.main --check-config >/dev/null 2>&1; then
    echo "[run.sh] Configuration problems found:"
    python3 -m anna_robot.main --check-config | sed -n "/Problems found/,\$p"
    exit 1
fi

echo "[run.sh] Starting the healthcare robot..."
exec python3 -m anna_robot.main "$@"
