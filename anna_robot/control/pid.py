"""A single, well-behaved PID implementation used by every control loop.

The robot has three feedback sources (camera today, wheel encoders and IMU
later) and several actuators (drive wheels, head pan, head tilt). They all
share this one controller so there is exactly one place to reason about
anti-windup, derivative noise and output limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..utils import clamp, deadband


@dataclass(frozen=True)
class PidGains:
    """Tuning for one PID axis.

    ``kp``/``ki``/``kd`` are the usual gains. The remaining fields exist
    because a robot PID driven by a noisy 15 FPS camera needs them:

    - ``output_limit`` clamps the command to the actuator's real range.
    - ``integral_limit`` caps the integral term so a blocked robot cannot
      wind up a lurch that fires the moment it comes free.
    - ``derivative_filter_s`` low-passes the D term; raw D on pixel error is
      mostly detection jitter.
    - ``deadband`` ignores errors too small to be worth an actuator command,
      which stops hunting around the setpoint.
    """

    kp: float = 0.0
    ki: float = 0.0
    kd: float = 0.0
    output_limit: float = 1.0
    integral_limit: float = 0.5
    derivative_filter_s: float = 0.08
    deadband: float = 0.0

    def scaled(self, factor: float) -> "PidGains":
        """Return the same gains scaled by ``factor`` (for gain scheduling)."""
        return PidGains(
            kp=self.kp * factor,
            ki=self.ki * factor,
            kd=self.kd * factor,
            output_limit=self.output_limit,
            integral_limit=self.integral_limit,
            derivative_filter_s=self.derivative_filter_s,
            deadband=self.deadband,
        )


@dataclass
class PidDebug:
    """Last-computed terms, published to telemetry so tuning is observable."""

    error: float = 0.0
    proportional: float = 0.0
    integral: float = 0.0
    derivative: float = 0.0
    output: float = 0.0
    saturated: bool = False

    def as_dict(self) -> dict:
        return {
            "error": round(self.error, 4),
            "p": round(self.proportional, 4),
            "i": round(self.integral, 4),
            "d": round(self.derivative, 4),
            "out": round(self.output, 4),
            "sat": self.saturated,
        }


class PidController:
    """Discrete PID with conditional-integration anti-windup.

    Two details make it safe for a robot rather than a simulation:

    * The derivative is taken on the *measurement*, not the error, so a
      setpoint change (say, a new follow distance) cannot produce a
      derivative kick that jolts the wheels.
    * The integral only accumulates while the output is not saturated and
      the extra term would not push it further into saturation.
    """

    def __init__(self, gains: PidGains, name: str = "pid") -> None:
        self.gains = gains
        self.name = name
        self._integral = 0.0
        self._last_measurement: Optional[float] = None
        self._filtered_derivative = 0.0
        self.debug = PidDebug()

    def reset(self) -> None:
        """Clear all history. Call whenever the target is lost or re-acquired."""
        self._integral = 0.0
        self._last_measurement = None
        self._filtered_derivative = 0.0
        self.debug = PidDebug()

    @property
    def integral(self) -> float:
        return self._integral

    def update(self, setpoint: float, measurement: float, dt: float) -> float:
        """Run one PID step and return the clamped control output."""
        gains = self.gains
        if dt <= 0.0:
            return self.debug.output

        error = deadband(setpoint - measurement, gains.deadband)
        proportional = gains.kp * error

        # Derivative on measurement (note the sign) then low-pass filtered.
        if self._last_measurement is None:
            raw_derivative = 0.0
        else:
            raw_derivative = -(measurement - self._last_measurement) / dt
        self._last_measurement = measurement
        if gains.derivative_filter_s > 0.0:
            alpha = dt / (gains.derivative_filter_s + dt)
            self._filtered_derivative += alpha * (raw_derivative - self._filtered_derivative)
        else:
            self._filtered_derivative = raw_derivative
        derivative = gains.kd * self._filtered_derivative

        # Conditional integration: try the step, keep it only if it does not
        # drive an already-saturated output further out of range.
        candidate_integral = clamp(
            self._integral + gains.ki * error * dt,
            -gains.integral_limit,
            gains.integral_limit,
        )
        unclamped = proportional + candidate_integral + derivative
        output = clamp(unclamped, -gains.output_limit, gains.output_limit)
        saturated = output != unclamped
        if not saturated or (candidate_integral * error) <= 0.0:
            self._integral = candidate_integral
            unclamped = proportional + self._integral + derivative
            output = clamp(unclamped, -gains.output_limit, gains.output_limit)
            saturated = output != unclamped

        self.debug = PidDebug(
            error=error,
            proportional=proportional,
            integral=self._integral,
            derivative=derivative,
            output=output,
            saturated=saturated,
        )
        return output
