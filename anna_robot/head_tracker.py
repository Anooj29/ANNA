"""Two-servo pan/tilt head that keeps the person centred in the frame.

ANNA's head carries the camera on a pan servo and a tilt servo. The tracker
closes a PID loop on the *pixel* error between the person and the centre of
the frame, so the person stays framed while the body drives (or stands
still) independently.

SAFETY - WHY THE TRAVEL IS LIMITED
----------------------------------
The camera ribbon and the microphone/speaker wiring run up through the neck.
Nothing here may ever ask the head to spin: a full rotation would twist and
eventually sever that loom. The limits are enforced in three independent
places, so no single mistake can defeat them:

1. :class:`~anna_robot.hardware.servo.ServoLimits` validates the configured
   range at construction and rejects anything outside +/-90 deg.
2. :class:`~anna_robot.hardware.servo.Servo` clamps every commanded angle
   *and* every value written to the PWM pin.
3. :class:`HeadTracker` clamps its own PID output to the same range and
   stops integrating once an axis reaches a limit, so the controller cannot
   wind up against the end stop.

Defaults are conservative (+/-70 deg pan, +/-30 deg tilt). Widen them only
after checking the real cable slack on the machine.

ANGLE CONVENTION
----------------
Positive pan turns the head **left**, positive tilt looks **up** - the same
right-hand convention the drive base uses for yaw, so "positive is left"
holds everywhere in the codebase. If a servo is mounted mirrored, flip it
with ``invert_pan`` / ``invert_tilt`` rather than by negating gains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from .control.pid import PidController, PidGains
from .control.visual import VisualTarget
from .hardware.servo import Servo, ServoLimits
from .utils import Deadline, clamp

logger = logging.getLogger(__name__)


class HeadState(str, Enum):
    DISABLED = "DISABLED"    # No servos configured.
    TRACKING = "TRACKING"    # Actively following a target.
    CENTERED = "CENTERED"    # Target lost; head returned to centre.
    RECENTERING = "RECENTER"  # On its way back to centre.
    AT_LIMIT = "AT_LIMIT"    # Tracking, but an axis is against its end stop.


@dataclass(frozen=True)
class HeadTuning:
    """How the head follows a target.

    The defaults favour calm motion over speed: a head that snaps around
    blurs the very frames the detector needs.
    """

    #: Normalised pixel error (0..1 of half-frame) ignored as "close enough".
    #: Also what stops the head hunting around a perfectly centred person.
    deadband: float = 0.06
    #: Degrees of correction per unit of normalised error.
    pan_gains: PidGains = PidGains(
        kp=18.0, ki=1.2, kd=2.2, output_limit=25.0, integral_limit=6.0,
        derivative_filter_s=0.12,
    )
    tilt_gains: PidGains = PidGains(
        kp=12.0, ki=0.8, kd=1.6, output_limit=18.0, integral_limit=4.0,
        derivative_filter_s=0.12,
    )
    #: Aim slightly above the box centre so a standing person's face, not
    #: their waist, ends up in the middle of the frame.
    tilt_bias: float = -0.18
    #: Seconds without a target before the head drifts back to centre.
    recenter_after_s: float = 3.0
    #: Degrees per second used for the (slow, unhurried) recentring move.
    recenter_speed_deg_s: float = 35.0


class HeadTracker:
    """Keeps a visual target centred using a pan servo and a tilt servo.

    Constructing with ``pan_pin=None`` and ``tilt_pin=None`` yields a
    disabled tracker that is safe to call - useful when the head is not
    fitted, and it keeps the robot's control loop free of ``if head:``
    branches.
    """

    def __init__(
        self,
        pan_pin: Optional[int] = None,
        tilt_pin: Optional[int] = None,
        pan_limits: Optional[ServoLimits] = None,
        tilt_limits: Optional[ServoLimits] = None,
        tuning: Optional[HeadTuning] = None,
        invert_pan: bool = False,
        invert_tilt: bool = False,
        enabled: bool = True,
    ) -> None:
        self.tuning = tuning or HeadTuning()
        self.pan_limits = pan_limits or ServoLimits(-70.0, 70.0, max_speed_deg_s=120.0)
        self.tilt_limits = tilt_limits or ServoLimits(-30.0, 30.0, max_speed_deg_s=90.0)
        self.state = HeadState.DISABLED

        self.pan: Optional[Servo] = None
        self.tilt: Optional[Servo] = None
        self.enabled = bool(enabled) and pan_pin is not None and tilt_pin is not None
        if self.enabled:
            try:
                self.pan = Servo(pan_pin, self.pan_limits, invert=invert_pan)
                self.tilt = Servo(tilt_pin, self.tilt_limits, invert=invert_tilt)
                self.state = HeadState.CENTERED
                logger.info(
                    "Head tracker active: pan pin %s (%.0f..%.0f deg), tilt pin %s (%.0f..%.0f deg).",
                    pan_pin, self.pan_limits.min_angle_deg, self.pan_limits.max_angle_deg,
                    tilt_pin, self.tilt_limits.min_angle_deg, self.tilt_limits.max_angle_deg,
                )
            except Exception:
                logger.exception("Head servos could not be initialised; head tracking is off.")
                self.enabled = False
        elif enabled:
            logger.info("Head tracking requested but no servo pins are configured; it stays off.")

        self._pan_pid = PidController(self.tuning.pan_gains, name="head-pan")
        self._tilt_pid = PidController(self.tuning.tilt_gains, name="head-tilt")
        self._idle = Deadline()
        self._lost_s = 0.0

    # -- geometry ---------------------------------------------------------
    @property
    def angles(self) -> Tuple[float, float]:
        """Current (pan, tilt) angles in degrees."""
        return (self.pan.angle if self.pan else 0.0, self.tilt.angle if self.tilt else 0.0)

    @property
    def at_limit(self) -> bool:
        return bool((self.pan and self.pan.at_limit) or (self.tilt and self.tilt.at_limit))

    def limits_as_dict(self) -> dict:
        return {
            "pan_min_deg": self.pan_limits.min_angle_deg,
            "pan_max_deg": self.pan_limits.max_angle_deg,
            "tilt_min_deg": self.tilt_limits.min_angle_deg,
            "tilt_max_deg": self.tilt_limits.max_angle_deg,
        }

    # -- control ----------------------------------------------------------
    def update(self, target: Optional[VisualTarget], dt: float) -> Tuple[float, float]:
        """Run one tracking step. Returns the resulting (pan, tilt) angles.

        Safe (and cheap) to call every frame whether or not the head exists
        or a target is visible.
        """
        if not self.enabled or self.pan is None or self.tilt is None or dt <= 0.0:
            return self.angles

        if target is None:
            self._track_nothing(dt)
        else:
            self._track(target, dt)

        # The servos do their own slew limiting, which is what turns each
        # PID step into smooth motion rather than a jump.
        self.pan.update(dt)
        self.tilt.update(dt)
        return self.angles

    def _track(self, target: VisualTarget, dt: float) -> None:
        self._lost_s = 0.0
        pan_error = clamp(target.bearing, -1.0, 1.0)
        tilt_error = clamp(target.elevation - self.tuning.tilt_bias, -1.0, 1.0)

        # Inside the deadband the head is already pointing at the person;
        # holding position keeps the image steady and the servos quiet.
        if abs(pan_error) <= self.tuning.deadband and abs(tilt_error) <= self.tuning.deadband:
            self.state = HeadState.AT_LIMIT if self.at_limit else HeadState.TRACKING
            return

        # Setpoint zero: the PID output is the correction in degrees, signed
        # so that a target to the right pans right (negative pan angle).
        pan_delta = self._pan_pid.update(setpoint=0.0, measurement=pan_error, dt=dt) * dt
        tilt_delta = self._tilt_pid.update(setpoint=0.0, measurement=tilt_error, dt=dt) * dt

        pan_target = self.pan_limits.clamp_angle(self.pan.target + pan_delta)
        tilt_target = self.tilt_limits.clamp_angle(self.tilt.target + tilt_delta)
        self.pan.command(pan_target)
        self.tilt.command(tilt_target)

        if self.at_limit:
            # Against an end stop the axis cannot reduce the error, so the
            # integrator is reset instead of winding up against the limit.
            self._reset_saturated_integrators()
            self.state = HeadState.AT_LIMIT
            logger.debug(
                "Head at travel limit (pan %.1f deg, tilt %.1f deg); the body turn takes over from here.",
                *self.angles,
            )
        else:
            self.state = HeadState.TRACKING

    def _reset_saturated_integrators(self) -> None:
        if self.pan is not None and self.pan.at_limit:
            self._pan_pid.reset()
        if self.tilt is not None and self.tilt.at_limit:
            self._tilt_pid.reset()

    def _track_nothing(self, dt: float) -> None:
        """No target: hold briefly (they may step back in), then recentre."""
        self._lost_s += dt
        if self._lost_s < self.tuning.recenter_after_s:
            return
        self._pan_pid.reset()
        self._tilt_pid.reset()

        step = self.tuning.recenter_speed_deg_s * dt
        pan_remaining = self.pan_limits.center_deg - self.pan.target
        tilt_remaining = self.tilt_limits.center_deg - self.tilt.target
        self.pan.command(self.pan.target + clamp(pan_remaining, -step, step))
        self.tilt.command(self.tilt.target + clamp(tilt_remaining, -step, step))

        settled = abs(pan_remaining) < 0.5 and abs(tilt_remaining) < 0.5
        self.state = HeadState.CENTERED if settled else HeadState.RECENTERING

    # -- manual control ---------------------------------------------------
    def look_at(self, pan_deg: float, tilt_deg: float) -> Tuple[float, float]:
        """Point the head at a specific angle (still clamped to the limits)."""
        if not self.enabled or self.pan is None or self.tilt is None:
            return self.angles
        self._pan_pid.reset()
        self._tilt_pid.reset()
        return self.pan.command(pan_deg), self.tilt.command(tilt_deg)

    def center(self) -> None:
        """Return the head to its neutral position."""
        if not self.enabled or self.pan is None or self.tilt is None:
            return
        self._pan_pid.reset()
        self._tilt_pid.reset()
        self.pan.center()
        self.tilt.center()
        self._lost_s = self.tuning.recenter_after_s

    def nod(self) -> None:
        """A small acknowledging tilt - used when ANNA answers a person."""
        if self.enabled and self.tilt is not None:
            self.tilt.command(self.tilt.target + 8.0)

    def as_dict(self) -> dict:
        """Head status for telemetry and the debug overlay."""
        pan_angle, tilt_angle = self.angles
        return {
            "enabled": self.enabled,
            "state": self.state.value,
            "pan_deg": round(pan_angle, 1),
            "tilt_deg": round(tilt_angle, 1),
            "at_limit": self.at_limit,
            **self.limits_as_dict(),
        }

    def close(self) -> None:
        """Centre the head and release both servos."""
        for servo in (self.pan, self.tilt):
            if servo is None:
                continue
            try:
                servo.center()
                servo.update(1.0)
                servo.close()
            except Exception:
                logger.debug("Head servo failed to close cleanly.", exc_info=True)
        self.enabled = False
        self.state = HeadState.DISABLED
