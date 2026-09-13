"""Hobby-servo driver with hard, non-negotiable travel limits.

ANNA's head carries the camera cable, so a servo that is free to sweep its
full range (let alone a continuous-rotation servo spinning past it) will wind
and eventually tear that cable. The limits therefore live *in the driver*:
:class:`ServoLimits` is validated at construction and every command is
clamped on the way out, so no caller - a PID, a test, or a future feature -
can drive the head past the safe range even by accident.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from ..utils import clamp, slew
from .gpio import get_gpio

logger = logging.getLogger(__name__)

#: Absolute travel a standard hobby servo can reach; configuration is
#: rejected outside this, which is the guard against a "360 degree" typo.
ABSOLUTE_MIN_ANGLE_DEG = -90.0
ABSOLUTE_MAX_ANGLE_DEG = 90.0


@dataclass(frozen=True)
class ServoLimits:
    """Validated travel and speed envelope for one servo axis.

    Angles are relative to the mechanical centre: 0 deg looks straight
    ahead. Signs follow the same right-hand convention as the drive base -
    **positive pan turns left, positive tilt looks up** - so a positive yaw
    command means the same thing whether it reaches the wheels or the neck.
    Use ``Servo(invert=True)`` when a servo is mounted mirrored.
    """

    min_angle_deg: float = -70.0
    max_angle_deg: float = 70.0
    max_speed_deg_s: float = 120.0
    center_deg: float = 0.0

    def __post_init__(self) -> None:
        if self.min_angle_deg >= self.max_angle_deg:
            raise ValueError(
                f"Servo min angle ({self.min_angle_deg}) must be below max angle ({self.max_angle_deg})."
            )
        if self.min_angle_deg < ABSOLUTE_MIN_ANGLE_DEG or self.max_angle_deg > ABSOLUTE_MAX_ANGLE_DEG:
            raise ValueError(
                f"Servo travel {self.min_angle_deg}..{self.max_angle_deg} deg leaves the safe range "
                f"{ABSOLUTE_MIN_ANGLE_DEG}..{ABSOLUTE_MAX_ANGLE_DEG} deg. Wider travel would wind the "
                "head cabling - widen the mechanical design before widening this limit."
            )
        if self.max_speed_deg_s <= 0.0:
            raise ValueError("Servo max speed must be positive.")
        if not self.min_angle_deg <= self.center_deg <= self.max_angle_deg:
            raise ValueError(
                f"Servo centre ({self.center_deg}) is outside its own travel limits."
            )

    def clamp_angle(self, angle_deg: float) -> float:
        return clamp(angle_deg, self.min_angle_deg, self.max_angle_deg)

    @property
    def travel_deg(self) -> float:
        return self.max_angle_deg - self.min_angle_deg


class Servo:
    """A single PWM-driven servo axis.

    Motion is slew-rate limited toward the commanded angle, so a large step
    from the tracker becomes a smooth sweep rather than a snap that shakes
    the camera (and the image the tracker depends on).
    """

    def __init__(
        self,
        pin: int,
        limits: ServoLimits,
        pwm_freq_hz: float = 50.0,
        min_pulse_ms: float = 0.5,
        max_pulse_ms: float = 2.5,
        invert: bool = False,
        idle_release_s: float = 2.0,
    ) -> None:
        if min_pulse_ms >= max_pulse_ms:
            raise ValueError("Servo min_pulse_ms must be below max_pulse_ms.")

        self.pin = int(pin)
        self.limits = limits
        self.invert = bool(invert)
        self.idle_release_s = max(float(idle_release_s), 0.0)

        self._gpio = get_gpio()
        self._pwm_freq_hz = float(pwm_freq_hz)
        self._min_pulse_ms = float(min_pulse_ms)
        self._max_pulse_ms = float(max_pulse_ms)
        self._lock = threading.Lock()
        self._angle = limits.center_deg
        self._target = limits.center_deg
        self._idle_s = 0.0
        self._attached = False

        self._gpio.setup(self.pin, self._gpio.OUT)
        self._pwm = self._gpio.PWM(self.pin, self._pwm_freq_hz)
        self._pwm.start(0.0)
        self._write(self._angle)

    # -- conversions ------------------------------------------------------
    def _angle_to_duty(self, angle_deg: float) -> float:
        """Map a clamped angle onto the servo's pulse width, as duty percent."""
        span = ABSOLUTE_MAX_ANGLE_DEG - ABSOLUTE_MIN_ANGLE_DEG
        fraction = (angle_deg - ABSOLUTE_MIN_ANGLE_DEG) / span
        pulse_ms = self._min_pulse_ms + fraction * (self._max_pulse_ms - self._min_pulse_ms)
        period_ms = 1000.0 / self._pwm_freq_hz
        return clamp(pulse_ms / period_ms * 100.0, 0.0, 100.0)

    def _write(self, angle_deg: float) -> None:
        # Belt and braces: clamp here too, so the PWM line cannot be driven
        # outside the safe envelope even if a caller bypasses `command`.
        safe_angle = self.limits.clamp_angle(angle_deg)
        output_angle = -safe_angle if self.invert else safe_angle
        self._pwm.ChangeDutyCycle(self._angle_to_duty(output_angle))
        self._attached = True

    # -- commands ---------------------------------------------------------
    @property
    def angle(self) -> float:
        with self._lock:
            return self._angle

    @property
    def target(self) -> float:
        with self._lock:
            return self._target

    @property
    def at_limit(self) -> bool:
        with self._lock:
            return self._angle <= self.limits.min_angle_deg or self._angle >= self.limits.max_angle_deg

    def command(self, angle_deg: float) -> float:
        """Set the target angle (clamped). Returns the accepted target."""
        with self._lock:
            self._target = self.limits.clamp_angle(float(angle_deg))
            return self._target

    def nudge(self, delta_deg: float) -> float:
        """Move the target by ``delta_deg``, still clamped to the limits."""
        with self._lock:
            target = self.limits.clamp_angle(self._target + float(delta_deg))
            self._target = target
        return target

    def update(self, dt: float) -> float:
        """Advance the axis toward its target; call once per control tick."""
        with self._lock:
            max_step = self.limits.max_speed_deg_s * max(dt, 0.0)
            new_angle = self.limits.clamp_angle(slew(self._angle, self._target, max_step))
            moved = abs(new_angle - self._angle) > 1e-3
            self._angle = new_angle
            angle = new_angle

        if moved:
            self._idle_s = 0.0
            self._write(angle)
        elif self.idle_release_s > 0.0:
            # Holding a stationary servo makes it buzz, draw current and heat
            # up. Once it has settled, drop the pulse until it is needed.
            self._idle_s += max(dt, 0.0)
            if self._attached and self._idle_s >= self.idle_release_s:
                self.release()
        return angle

    def center(self) -> None:
        self.command(self.limits.center_deg)

    def release(self) -> None:
        """Stop driving the servo (it holds position passively)."""
        self._pwm.ChangeDutyCycle(0.0)
        self._attached = False

    def close(self) -> None:
        try:
            self.release()
            self._pwm.stop()
        except Exception:
            logger.debug("Servo on pin %s failed to stop cleanly.", self.pin, exc_info=True)
