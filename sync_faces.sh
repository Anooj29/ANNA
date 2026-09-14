#!/usr/bin/env bash
# Cloud DB + photo download only (minimal deps: psycopg2-binary, requests).
# Does not import RPi.GPIO or the full robot.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source ".env"
    set +a
fi

VENV_DIR="${VENV_DIR:-.venv}"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

pip install -q psycopg2-binary requests
exec python3 -m anna_robot.sync_main "$@"
