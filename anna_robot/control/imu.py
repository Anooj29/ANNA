"""IMU feedback segment - wired up, switched off until an IMU is fitted.

Like the encoder segment, this exists so the future upgrade is a
configuration change rather than a refactor. It is disabled by default
(``ROBOT_IMU_ENABLED=false``).

The driver is deliberately pluggable: :class:`ImuReader` is the two-method
contract an MPU6050/BNO055 backend has to satisfy, and
:class:`SimulatedImuReader` stands in until one exists, so the fusion logic
below can be developed and unit tested today.

Why it matters later: a gyro measures the turn ANNA actually made, including
the part the wheels lost to slip on a polished ward floor, and it does so at
a far higher rate than the camera. Heading control gets much crisper once it
is available.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Optional, Protocol, Tuple, runtime_checkable

from ..utils import ExponentialFilter
from .feedback import BaseFeedbackSource, MotionEstimate

logger = logging.getLogger(__name__)


@runtime_checkable
class ImuReader(Protocol):
    """Minimal contract a real IMU driver must satisfy."""

    def read_gyro_rps(self) -> Tuple[float, float, float]:
        """Angular rate (x, y, z) in rad/s."""

    def read_accel_mps2(self) -> Tuple[float, float, float]:
        """Linear acceleration (x, y, z) in m/s^2, gravity included."""


class SimulatedImuReader:
    """A quiet, still IMU. Placeholder until real hardware is wired in."""

    def read_gyro_rps(self) -> Tuple[float, float, float]:
        return (0.0, 0.0, 0.0)

    def read_accel_mps2(self) -> Tuple[float, float, float]:
        return (0.0, 0.0, 9.81)


class ImuFeedback(BaseFeedbackSource):
    """Yaw-rate and heading feedback from a 6-axis IMU.

    Gyro bias is estimated while the robot is known to be still
    (:meth:`calibrate`), because an uncorrected bias of even 0.01 rad/s turns
    into 35 degrees of phantom heading drift per minute.
    """

    def __init__(
        self,
        reader: Optional[ImuReader] = None,
        enabled: bool = False,
        gyro_filter_s: float = 0.05,
        yaw_axis: int = 2,
    ) -> None:
        super().__init__(name="imu", enabled=enabled)
        self._reader = reader or SimulatedImuReader()
        self._is_real_hardware = reader is not None
        self._yaw_axis = int(yaw_axis)
        self._yaw_filter = ExponentialFilter(gyro_filter_s)
        self._bias_rps = 0.0
        self._heading_rad = 0.0
        self._last_poll = time.monotonic()

        if self.enabled and not self._is_real_hardware:
            logger.warning(
                "IMU feedback enabled but no driver was supplied; using the simulated "
                "reader, which always reports 'perfectly still'."
            )

    def calibrate(self, samples: int = 100, delay_s: float = 0.005) -> float:
        """Average the yaw gyro while stationary to estimate its bias."""
        total = 0.0
        taken = 0
        for _ in range(max(samples, 1)):
            try:
                total += self._reader.read_gyro_rps()[self._yaw_axis]
                taken += 1
            except Exception:
                logger.exception("IMU read failed during calibration.")
                break
            if delay_s > 0:
                time.sleep(delay_s)
        self._bias_rps = total / taken if taken else 0.0
        logger.info("IMU yaw bias calibrated to %.5f rad/s over %d samples.", self._bias_rps, taken)
        return self._bias_rps

    def poll(self) -> MotionEstimate:
        now = time.monotonic()
        dt = now - self._last_poll
        self._last_poll = now
        if not self.enabled or dt <= 0.0:
            self._last = MotionEstimate(confidence=0.0, timestamp=now)
            return self._last

        try:
            yaw_rate = self._reader.read_gyro_rps()[self._yaw_axis] - self._bias_rps
        except Exception:
            logger.exception("IMU read failed; reporting no confidence this tick.")
            self._last = MotionEstimate(confidence=0.0, timestamp=now)
            return self._last

        filtered = self._yaw_filter.update(yaw_rate, dt)
        self._heading_rad = _wrap_angle(self._heading_rad + filtered * dt)
        self._last = MotionEstimate(
            angular_velocity_rps=filtered,
            heading_rad=self._heading_rad,
            # A simulated reader must never outrank a real camera.
            confidence=0.85 if self._is_real_hardware else 0.0,
            timestamp=now,
        )
        return self._last

    @property
    def heading_deg(self) -> float:
        return math.degrees(self._heading_rad)

    def reset(self) -> None:
        super().reset()
        self._heading_rad = 0.0
        self._yaw_filter.reset()
        self._last_poll = time.monotonic()


def _wrap_angle(angle_rad: float) -> float:
    """Normalise an angle to (-pi, pi]."""
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi
