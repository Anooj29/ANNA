#!/usr/bin/env bash
# Run the robot stack without physical GPIO / motor / ECG wiring.
# Same as: ROBOT_SIMULATE_HARDWARE=true ./run.sh [args...]
#
# Examples:
#   ./software.sh --no-debug-window
#   ./software.sh --simulate-hardware   # redundant if env is set, but harmless

set -euo pipefail

export ROBOT_SIMULATE_HARDWARE=true
export ROBOT_SIMULATE_CAMERA=true
exec "$(dirname "$0")/run.sh" "$@"
