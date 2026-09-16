"""Differential-drive motor control with ramped, mixed velocity commands.

Two layers live here:

* :meth:`MotorController.drive` - the modern interface the PID follower
  uses. It takes normalised linear/angular commands, mixes them into wheel
  duties, and *ramps* toward them so the chassis accelerates smoothly
  instead of lurching (which is what makes following a person look calm and
  keeps the camera image steady enough to track).
* :meth:`forward` / :meth:`turn_left` / :meth:`turn_right` / :meth:`stop` -
  the original fixed-duty interface, kept working unchanged so existing
  behaviour and any external callers keep functioning.

Hardware note: the wiring only drives the motors forward - steering is done
by biasing the duty cycle between the wheels. Reverse is therefore refused
unless ``allow_reverse`` is enabled for a board that supports it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from .hardware.gpio import get_gpio
from .utils import clamp, slew

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MotorTuning:
    """Duty-cycle envelope and acceleration limits for the drive base."""

    #: Duty below which the motors buzz but do not turn (stiction).
    min_duty: float = 22.0
    #: Highest duty the follower is allowed to command.
    max_duty: float = 55.0
    #: Duty used by the legacy fixed-speed helpers.
    cruise_duty: float = 50.0
    #: Duty of the slowed wheel in a legacy fixed-speed turn.
    turn_duty: float = 25.0
    #: Acceleration limit, duty-percent per second. Lower = gentler.
    ramp_duty_per_s: float = 60.0
    #: Longest time step the ramp will honour, seconds. A slow frame (model
    #: warm-up, a camera hiccup) must not let the wheels jump to full duty.
    max_ramp_dt_s: float = 0.1
    #: PWM carrier frequency.
    pwm_freq_hz: int = 1000

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_duty < self.max_duty <= 100.0:
            raise ValueError("Motor duties must satisfy 0 <= min_duty < max_duty <= 100.")
        if self.ramp_duty_per_s <= 0.0:
            raise ValueError("ramp_duty_per_s must be positive.")
        if self.max_ramp_dt_s <= 0.0:
            raise ValueError("max_ramp_dt_s must be positive.")


class MotorController:
    def __init__(
        self,
        left_dir: int,
        left_pwm: int,
        right_dir: int,
        right_pwm: int,
        tuning: Optional[MotorTuning] = None,
        allow_reverse: bool = False,
        pwm_freq_hz: Optional[int] = None,
    ) -> None:
        self.tuning = tuning or MotorTuning()
        self.allow_reverse = bool(allow_reverse)

        self._gpio = get_gpio()
        for pin in (left_dir, right_dir, left_pwm, right_pwm):
            self._gpio.setup(pin, self._gpio.OUT)
        self._left_dir = left_dir
        self._right_dir = right_dir

        frequency = int(pwm_freq_hz or self.tuning.pwm_freq_hz)
        self._left_motor = self._gpio.PWM(left_pwm, frequency)
        self._right_motor = self._gpio.PWM(right_pwm, frequency)
        self._left_motor.start(0)
        self._right_motor.start(0)
        self._gpio.output(self._left_dir, 0)
        self._gpio.output(self._right_dir, 0)

        self._applied: Tuple[float, float] = (0.0, 0.0)
        self._requested: Tuple[float, float] = (0.0, 0.0)
        self._reversed = False
        self._last_update = time.monotonic()
        self._closed = False

    # -- low-level --------------------------------------------------------
    @property
    def duties(self) -> Tuple[float, float]:
        """The duty cycles currently on the pins, as (left, right)."""
        return self._applied

    @property
    def is_moving(self) -> bool:
        return any(duty > 0.0 for duty in self._applied)

    def _write(self, left_duty: float, right_duty: float, reverse: bool = False) -> None:
        if reverse and not self.allow_reverse:
            reverse = False
        if reverse != self._reversed:
            self._gpio.output(self._left_dir, 1 if reverse else 0)
            self._gpio.output(self._right_dir, 1 if reverse else 0)
            self._reversed = reverse
        left_duty = clamp(left_duty, 0.0, 100.0)
        right_duty = clamp(right_duty, 0.0, 100.0)
        self._left_motor.ChangeDutyCycle(left_duty)
        self._right_motor.ChangeDutyCycle(right_duty)
        self._applied = (left_duty, right_duty)

    def _ramp_towards(self, left_duty: float, right_duty: float, dt: Optional[float]) -> None:
        """Apply the requested duties subject to the acceleration limit."""
        now = time.monotonic()
        if dt is None:
            dt = now - self._last_update
        self._last_update = now

        # Cap the step: a long gap since the last update (start-up, a stalled
        # frame) would otherwise allow an instant jump to the target duty.
        # A zero step holds the current duty rather than jumping, because
        # ``slew`` treats a non-positive limit as "no limit".
        dt = clamp(dt, 0.0, self.tuning.max_ramp_dt_s)
        if dt <= 0.0:
            self._requested = (left_duty, right_duty)
            return
        max_step = self.tuning.ramp_duty_per_s * dt
        applied_left = slew(self._applied[0], left_duty, max_step)
        applied_right = slew(self._applied[1], right_duty, max_step)
        self._requested = (left_duty, right_duty)
        self._write(applied_left, applied_right, reverse=self._reversed)

    def _scale_to_duty(self, magnitude: float) -> float:
        """Map a 0..1 wheel command onto the usable duty band.

        Below the stiction floor the wheel only buzzes, so anything that
        small is commanded as a true stop rather than a stall.
        """
        magnitude = clamp(abs(magnitude), 0.0, 1.0)
        if magnitude < 1e-3:
            return 0.0
        span = self.tuning.max_duty - self.tuning.min_duty
        return self.tuning.min_duty + magnitude * span

    # -- modern interface -------------------------------------------------
    @staticmethod
    def mix(linear: float, angular: float) -> Tuple[float, float]:
        """Mix normalised linear/angular commands into wheel commands.

        ``linear`` is forward speed (-1..1) and ``angular`` is yaw rate
        (-1..1, positive turns left). The pair is rescaled rather than
        clipped when it would exceed full scale, so a hard turn keeps its
        requested *shape* instead of quietly straightening out.
        """
        linear = clamp(linear, -1.0, 1.0)
        angular = clamp(angular, -1.0, 1.0)
        left = linear - angular
        right = linear + angular
        peak = max(abs(left), abs(right))
        if peak > 1.0:
            left /= peak
            right /= peak
        return left, right

    def drive(self, linear: float, angular: float, dt: Optional[float] = None) -> Tuple[float, float]:
        """Command a ramped velocity. Returns the wheel duties applied."""
        if self._closed:
            return self._applied
        left_cmd, right_cmd = self.mix(linear, angular)

        # Forward-only wiring: a negative mix would run a wheel backwards,
        # which this driver cannot do, so it is commanded to a stop instead.
        if not self.allow_reverse:
            left_cmd = max(left_cmd, 0.0)
            right_cmd = max(right_cmd, 0.0)

        self._ramp_towards(self._scale_to_duty(left_cmd), self._scale_to_duty(right_cmd), dt)
        logger.debug(
            "Motor: drive linear=%.2f angular=%.2f -> duties L=%.1f R=%.1f",
            linear, angular, self._applied[0], self._applied[1],
        )
        return self._applied

    def coast(self, dt: Optional[float] = None) -> None:
        """Ramp smoothly down to a stop (gentler than :meth:`stop`)."""
        self._ramp_towards(0.0, 0.0, dt)

    # -- original fixed-speed interface (unchanged behaviour) -------------
    def forward(self) -> None:
        self._write(self.tuning.cruise_duty, self.tuning.cruise_duty)
        logger.debug("Motor: forward")

    def turn_left(self) -> None:
        self._write(self.tuning.turn_duty, self.tuning.cruise_duty)
        logger.debug("Motor: left")

    def turn_right(self) -> None:
        self._write(self.tuning.cruise_duty, self.tuning.turn_duty)
        logger.debug("Motor: right")

    def stop(self) -> None:
        """Stop immediately, bypassing the ramp (this is the safety path)."""
        self._requested = (0.0, 0.0)
        self._write(0.0, 0.0)
        self._last_update = time.monotonic()
        logger.debug("Motor: stop")

    def close(self) -> None:
        """Stop the motors and release the PWM channels."""
        if self._closed:
            return
        try:
            self.stop()
            self._left_motor.stop()
            self._right_motor.stop()
        except Exception:
            logger.debug("Motor PWM failed to stop cleanly.", exc_info=True)
        finally:
            self._closed = True
