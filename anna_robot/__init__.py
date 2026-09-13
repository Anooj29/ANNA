"""ANNA - healthcare assistant robot package.

Layout:

* :mod:`anna_robot.robot`        - the state machine that ties it together
* :mod:`anna_robot.config`       - environment-driven configuration
* :mod:`anna_robot.control`      - PID control and the feedback segments
  (visual today; wheel-encoder and IMU ready for future hardware)
* :mod:`anna_robot.perception`   - object detection, tracking, face and
  emotion recognition
* :mod:`anna_robot.interaction`  - wake words, intents and dialogue
* :mod:`anna_robot.head_tracker` - the two-servo head that keeps a person
  centred in frame, within hard travel limits
* :mod:`anna_robot.hardware`     - GPIO, camera and servo access, with a
  simulation fallback so everything runs off-Pi
* :mod:`anna_robot.sensors`      - ultrasonic, temperature, pulse, ECG

See README.md at the repository root for hardware requirements, setup and
run instructions.
"""

__version__ = "2.0.0"
