"""Wheel-encoder feedback segment - wired up, switched off until fitted.

ANNA has no encoders on the wheels yet, so this source is disabled by
default (``ROBOT_ENCODER_ENABLED=false``) and reports zero confidence, which
means the feedback bus simply never selects it. Everything needed to bring
it online is here: quadrature counting on GPIO edges, tick-to-metre
conversion, and differential-drive odometry. When the hardware arrives, set
the pins and the enable flag - no controller code has to change.

Why it matters later: vision tells ANNA where the *person* is, but it cannot
tell her how far *she* actually moved. Encoders close that gap and let the
follower hold a distance through a momentary detection dropout.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

from ..hardware.gpio import get_gpio
from .feedback import BaseFeedbackSource, MotionEstimate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EncoderGeometry:
    """Physical constants needed to turn ticks into metres and radians."""

    ticks_per_revolution: int = 20
    wheel_diameter_m: float = 0.065
    wheel_base_m: float = 0.20
    gear_ratio: float = 1.0

    def __post_init__(self) -> None:
        if self.ticks_per_revolution <= 0:
            raise ValueError("ticks_per_revolution must be positive.")
        if self.wheel_diameter_m <= 0 or self.wheel_base_m <= 0:
            raise ValueError("Wheel diameter and wheel base must be positive.")
        if self.gear_ratio <= 0:
            raise ValueError("gear_ratio must be positive.")

    @property
    def metres_per_tick(self) -> float:
        revolutions_per_tick = 1.0 / (self.ticks_per_revolution * self.gear_ratio)
        return math.pi * self.wheel_diameter_m * revolutions_per_tick


class WheelEncoderFeedback(BaseFeedbackSource):
    """Differential-drive odometry from two wheel encoders.

    Counting happens in GPIO edge callbacks (or via :meth:`inject_ticks` in
    tests and simulation); :meth:`poll` only does arithmetic, so it is safe
    to call from the control loop every tick.
    """

    def __init__(
        self,
        left_pin: Optional[int] = None,
        right_pin: Optional[int] = None,
        geometry: Optional[EncoderGeometry] = None,
        enabled: bool = False,
    ) -> None:
        super().__init__(name="encoder", enabled=enabled)
        self.geometry = geometry or EncoderGeometry()
        self.left_pin = left_pin
        self.right_pin = right_pin

        self._lock = threading.Lock()
        self._left_ticks = 0
        self._right_ticks = 0
        self._last_left = 0
        self._last_right = 0
        self._last_poll = time.monotonic()
        self._heading_rad = 0.0
        self._distance_m = 0.0
        self._attached = False

        if self.enabled and left_pin is not None and right_pin is not None:
            self._attach(left_pin, right_pin)
        elif self.enabled:
            logger.warning("Encoder feedback enabled but no pins configured; it will report nothing.")
            self.enabled = False

    def _attach(self, left_pin: int, right_pin: int) -> None:
        gpio = get_gpio()
        try:
            gpio.setup(left_pin, gpio.IN, pull_up_down=gpio.PUD_UP)
            gpio.setup(right_pin, gpio.IN, pull_up_down=gpio.PUD_UP)
            gpio.add_event_detect(left_pin, gpio.RISING, callback=self._on_left, bouncetime=1)
            gpio.add_event_detect(right_pin, gpio.RISING, callback=self._on_right, bouncetime=1)
            self._attached = True
            logger.info("Wheel encoders attached on pins %s/%s.", left_pin, right_pin)
        except Exception:
            logger.exception("Could not attach wheel encoders; disabling the source.")
            self.enabled = False

    # -- tick capture -----------------------------------------------------
    def _on_left(self, _pin: int) -> None:  # pragma: no cover - GPIO callback
        self.inject_ticks(left=1, right=0)

    def _on_right(self, _pin: int) -> None:  # pragma: no cover - GPIO callback
        self.inject_ticks(left=0, right=1)

    def inject_ticks(self, left: int, right: int) -> None:
        """Add ticks directly. Used by the GPIO callbacks and by tests."""
        with self._lock:
            self._left_ticks += int(left)
            self._right_ticks += int(right)

    @property
    def ticks(self) -> tuple:
        with self._lock:
            return self._left_ticks, self._right_ticks

    # -- odometry ---------------------------------------------------------
    def poll(self) -> MotionEstimate:
        now = time.monotonic()
        with self._lock:
            left_delta = self._left_ticks - self._last_left
            right_delta = self._right_ticks - self._last_right
            self._last_left = self._left_ticks
            self._last_right = self._right_ticks
            dt = now - self._last_poll
            self._last_poll = now

            if not self.enabled or dt <= 0.0:
                self._last = MotionEstimate(confidence=0.0, timestamp=now)
                return self._last

            metres_per_tick = self.geometry.metres_per_tick
            left_m = left_delta * metres_per_tick
            right_m = right_delta * metres_per_tick
            linear_m = (left_m + right_m) / 2.0
            angular_rad = (right_m - left_m) / self.geometry.wheel_base_m

            self._distance_m += linear_m
            self._heading_rad = _wrap_angle(self._heading_rad + angular_rad)

            self._last = MotionEstimate(
                linear_velocity_mps=linear_m / dt,
                angular_velocity_rps=angular_rad / dt,
                heading_rad=self._heading_rad,
                distance_m=self._distance_m,
                # Encoders are precise but blind to wheel slip, so they are
                # trusted highly - never absolutely.
                confidence=0.9 if self._attached else 0.5,
                timestamp=now,
            )
            return self._last

    def reset(self) -> None:
        with self._lock:
            self._left_ticks = self._right_ticks = 0
            self._last_left = self._last_right = 0
            self._heading_rad = 0.0
            self._distance_m = 0.0
            self._last_poll = time.monotonic()
        self._last = MotionEstimate(confidence=0.0)

    def close(self) -> None:
        if not self._attached:
            return
        gpio = get_gpio()
        for pin in (self.left_pin, self.right_pin):
            if pin is None:
                continue
            try:
                gpio.remove_event_detect(pin)
            except Exception:
                logger.debug("Could not detach encoder interrupt on pin %s.", pin, exc_info=True)
        self._attached = False


def _wrap_angle(angle_rad: float) -> float:
    """Normalise an angle to (-pi, pi]."""
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi
