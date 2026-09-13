"""Hardware access layer: GPIO backend, camera capture and servo driver.

Every module below hides one piece of hardware behind a small, testable API
and degrades gracefully when that hardware is missing, which is what lets the
whole robot stack import and run on a development machine.
"""

from .camera import CameraError, ThreadedCamera
from .gpio import backend_name, get_gpio, is_simulated, reset_backend, use_simulation
from .servo import ABSOLUTE_MAX_ANGLE_DEG, ABSOLUTE_MIN_ANGLE_DEG, Servo, ServoLimits

__all__ = [
    "ABSOLUTE_MAX_ANGLE_DEG",
    "ABSOLUTE_MIN_ANGLE_DEG",
    "CameraError",
    "Servo",
    "ServoLimits",
    "ThreadedCamera",
    "backend_name",
    "get_gpio",
    "is_simulated",
    "reset_backend",
    "use_simulation",
]
