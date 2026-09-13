"""HC-SR04 ultrasonic distance sensor, sampled off the control loop.

Measuring an HC-SR04 costs a 20 ms settle plus up to two echo timeouts -
around 60 ms of pure blocking in the worst case. Doing that inline capped
the old control loop at roughly 15 FPS *before* any vision work, and a
single spurious echo would slam the robot to a stop.

So: a background thread samples at a fixed rate and publishes a
median-filtered distance the control loop can read instantly. The median is
what rejects the occasional wild reading these sensors produce without
adding the lag a moving average would.
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from collections import deque
from typing import Deque, Optional

from ..hardware.gpio import get_gpio, is_simulated

logger = logging.getLogger(__name__)

#: Speed of sound (cm/s) halved, because the pulse makes a round trip.
_SPEED_OF_SOUND_HALF_CM_S = 17150.0


class UltrasonicSensor:
    """Distance in centimetres, sampled in the background."""

    NO_ECHO_DISTANCE_CM = 999.0
    #: Readings outside this range are physically impossible for an HC-SR04.
    MIN_VALID_CM = 2.0
    MAX_VALID_CM = 400.0

    def __init__(
        self,
        trig_pin: int,
        echo_pin: int,
        pulse_timeout_s: float = 0.04,
        sample_interval_s: float = 0.06,
        window: int = 5,
        background: bool = True,
    ) -> None:
        self._gpio = get_gpio()
        self._gpio.setup(trig_pin, self._gpio.OUT)
        self._gpio.setup(echo_pin, self._gpio.IN)
        self._trig = trig_pin
        self._echo = echo_pin
        self._timeout = float(pulse_timeout_s)
        self._sample_interval = float(sample_interval_s)
        self._readings: Deque[float] = deque(maxlen=max(int(window), 1))
        self._lock = threading.Lock()
        self._last_raw = self.NO_ECHO_DISTANCE_CM
        self._simulated = is_simulated()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        if self._simulated:
            logger.info("Ultrasonic sensor running in simulation; it reports a constant clear path.")
        if background:
            self._thread = threading.Thread(target=self._run, name="ultrasonic", daemon=True)
            self._thread.start()

    # -- sampling ---------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample()
            self._stop.wait(self._sample_interval)

    def sample(self) -> float:
        """Take one raw measurement and fold it into the filter window."""
        distance = self._measure_once()
        with self._lock:
            self._last_raw = distance
            if self.MIN_VALID_CM <= distance <= self.MAX_VALID_CM:
                self._readings.append(distance)
            elif distance >= self.NO_ECHO_DISTANCE_CM:
                # A clean "nothing in range" is information too: let it push
                # the old readings out rather than holding a stale obstacle.
                self._readings.append(self.MAX_VALID_CM)
        return distance

    def _measure_once(self) -> float:
        if self._simulated:
            return self.MAX_VALID_CM

        gpio = self._gpio
        gpio.output(self._trig, False)
        time.sleep(0.002)
        gpio.output(self._trig, True)
        time.sleep(0.00001)
        gpio.output(self._trig, False)

        # Wait for the echo to start. The deadline is measured from *here*,
        # not from before the trigger, so the timeout means what it says.
        deadline = time.monotonic() + self._timeout
        while gpio.input(self._echo) == 0:
            if time.monotonic() > deadline:
                return self.NO_ECHO_DISTANCE_CM
        pulse_start = time.monotonic()

        deadline = pulse_start + self._timeout
        while gpio.input(self._echo) == 1:
            if time.monotonic() > deadline:
                return self.NO_ECHO_DISTANCE_CM
        pulse_end = time.monotonic()

        return round((pulse_end - pulse_start) * _SPEED_OF_SOUND_HALF_CM_S, 2)

    # -- reading ----------------------------------------------------------
    def measure_cm(self) -> float:
        """The current filtered distance. Instant - never blocks the loop.

        Falls back to measuring inline if the background thread is off, so
        the original synchronous behaviour is still available.
        """
        if self._thread is None:
            self.sample()
        with self._lock:
            if not self._readings:
                return self._last_raw
            return round(statistics.median(self._readings), 2)

    @property
    def raw_cm(self) -> float:
        """The most recent unfiltered reading (diagnostics)."""
        with self._lock:
            return self._last_raw

    @property
    def is_obstructed(self) -> bool:
        return self.measure_cm() < self.MIN_VALID_CM * 2

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
