"""One place that decides how GPIO pins are driven.

On a Raspberry Pi this hands back the real ``RPi.GPIO`` module. Anywhere
else (a laptop, CI, a unit test) it hands back a simulated backend with the
same API, so the entire package imports and runs without the hardware
attached. Every module that touches a pin goes through :func:`get_gpio`
instead of importing ``RPi.GPIO`` directly, which is what makes the robot
logic testable and keeps the "is this a Pi?" question in a single file.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Set by :func:`use_simulation` / :func:`get_gpio`; read via :func:`backend_name`.
_backend: Optional[Any] = None
_backend_name: str = "uninitialised"
_lock = threading.Lock()


class SimulatedPWM:
    """Stand-in for ``RPi.GPIO.PWM`` that just records what it was told."""

    def __init__(self, owner: "SimulatedGPIO", pin: int, frequency_hz: float) -> None:
        self._owner = owner
        self._pin = pin
        self.frequency_hz = float(frequency_hz)
        self.duty_cycle = 0.0
        self.running = False

    def start(self, duty_cycle: float) -> None:
        self.running = True
        self.ChangeDutyCycle(duty_cycle)

    def ChangeDutyCycle(self, duty_cycle: float) -> None:  # noqa: N802 - RPi.GPIO API
        self.duty_cycle = float(duty_cycle)
        self._owner.pwm_duty[self._pin] = self.duty_cycle

    def ChangeFrequency(self, frequency_hz: float) -> None:  # noqa: N802 - RPi.GPIO API
        self.frequency_hz = float(frequency_hz)

    def stop(self) -> None:
        self.running = False
        self.duty_cycle = 0.0
        self._owner.pwm_duty[self._pin] = 0.0


class SimulatedGPIO:
    """In-memory GPIO backend mirroring the subset of ``RPi.GPIO`` we use.

    Tests can drive it through :meth:`set_input` and inspect it through
    :attr:`outputs` / :attr:`pwm_duty`.
    """

    BCM = 11
    BOARD = 10
    OUT = 0
    IN = 1
    HIGH = 1
    LOW = 0
    PUD_OFF = 20
    PUD_DOWN = 21
    PUD_UP = 22
    RISING = 31
    FALLING = 32
    BOTH = 33

    def __init__(self) -> None:
        self.mode: Optional[int] = None
        self.warnings = True
        self.modes: Dict[int, int] = {}
        self.outputs: Dict[int, int] = {}
        self.inputs: Dict[int, int] = {}
        self.pwm_duty: Dict[int, float] = {}
        self.cleaned_up = False

    # -- configuration ----------------------------------------------------
    def setmode(self, mode: int) -> None:
        self.mode = mode

    def setwarnings(self, enabled: bool) -> None:
        self.warnings = bool(enabled)

    def setup(self, pin: int, direction: int, pull_up_down: int = PUD_OFF, initial: int = LOW) -> None:
        self.modes[pin] = direction
        if direction == self.OUT:
            self.outputs[pin] = initial
        else:
            self.inputs.setdefault(pin, self.HIGH if pull_up_down == self.PUD_UP else self.LOW)

    # -- I/O --------------------------------------------------------------
    def output(self, pin: int, value: int) -> None:
        self.outputs[pin] = int(bool(value))

    def input(self, pin: int) -> int:
        return self.inputs.get(pin, self.LOW)

    def PWM(self, pin: int, frequency_hz: float) -> SimulatedPWM:  # noqa: N802 - RPi.GPIO API
        return SimulatedPWM(self, pin, frequency_hz)

    def add_event_detect(self, pin: int, edge: int, callback=None, bouncetime: int = 0) -> None:
        """Accepted and ignored: nothing generates edges in simulation."""

    def remove_event_detect(self, pin: int) -> None:
        """Counterpart to :meth:`add_event_detect`; also a no-op."""

    def cleanup(self, pin: Optional[int] = None) -> None:
        self.cleaned_up = True
        if pin is None:
            self.outputs.clear()
            self.pwm_duty.clear()

    # -- test helpers -----------------------------------------------------
    def set_input(self, pin: int, value: int) -> None:
        self.inputs[pin] = int(bool(value))


def get_gpio(prefer_simulation: bool = False) -> Any:
    """Return the GPIO backend, initialising it on first use.

    ``prefer_simulation`` forces the simulated backend even on a Pi, which is
    how ``--simulate`` lets you exercise the full control stack on the bench
    with no motors wired up.
    """
    global _backend, _backend_name
    with _lock:
        if _backend is not None:
            return _backend
        if not prefer_simulation:
            try:
                import RPi.GPIO as real_gpio  # type: ignore[import-not-found]

                _backend = real_gpio
                _backend_name = "RPi.GPIO"
                logger.info("GPIO backend: RPi.GPIO (real hardware).")
                return _backend
            except Exception:
                logger.warning(
                    "RPi.GPIO is unavailable - falling back to the simulated GPIO "
                    "backend. Motors, servos and GPIO sensors will not move."
                )
        _backend = SimulatedGPIO()
        _backend_name = "simulated"
        return _backend


def use_simulation() -> SimulatedGPIO:
    """Force the simulated backend and return it (used by tests and --simulate)."""
    global _backend, _backend_name
    with _lock:
        _backend = SimulatedGPIO()
        _backend_name = "simulated"
        return _backend


def reset_backend() -> None:
    """Forget the cached backend so the next :func:`get_gpio` re-detects."""
    global _backend, _backend_name
    with _lock:
        _backend = None
        _backend_name = "uninitialised"


def backend_name() -> str:
    return _backend_name


def is_simulated() -> bool:
    return isinstance(_backend, SimulatedGPIO)
