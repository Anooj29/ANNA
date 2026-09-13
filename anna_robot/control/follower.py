"""Smooth person following built on visual feedback and two PID loops.

The behaviour that makes following feel smooth rather than twitchy is all
here, in layers:

1. **Two PIDs** - bearing error drives yaw, range error drives forward
   speed. Both run on the *smoothed* visual target, never on raw pixels.
2. **Cornering taper** - forward speed is scaled down while turning hard, so
   the robot arcs into line instead of swinging around its target.
3. **Arrival hysteresis** - once inside the comfort band the robot holds
   still and only sets off again after the person has moved a clear step
   away. Without this the robot creeps back and forth forever.
4. **Graceful loss** - when the target disappears the command decays toward
   zero over a short coast window before any search behaviour starts, so a
   one-frame dropout never produces a jerk.

Safety takes precedence over all of it: an obstacle inside the stop
distance zeroes forward motion regardless of what the PIDs want.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..utils import clamp, map_range, slew
from .pid import PidController, PidGains
from .visual import VisualTarget

logger = logging.getLogger(__name__)


class FollowState(str, Enum):
    IDLE = "IDLE"            # No target requested.
    SEARCHING = "SEARCHING"  # Target lost for a while; scanning for it.
    APPROACHING = "APPROACH"  # Closing the gap to the person.
    HOLDING = "HOLDING"      # At a comfortable distance, standing by.
    BLOCKED = "BLOCKED"      # Obstacle inside the safety distance.
    LOST = "LOST"            # Just lost the target; coasting to a stop.


@dataclass(frozen=True)
class FollowTuning:
    """Everything that shapes how following feels."""

    #: Distance the robot tries to hold, in cm.
    target_distance_cm: float = 90.0
    #: Half-width of the "close enough, stand still" band, in cm.
    hold_band_cm: float = 18.0
    #: Range error that corresponds to a full-scale forward command. Having
    #: this makes the range gains dimensionless, exactly like the bearing
    #: gains, so the two loops can be reasoned about on the same scale.
    range_scale_cm: float = 120.0
    #: Extra distance the person must gain before the robot sets off again.
    resume_margin_cm: float = 12.0
    #: Hard stop: obstacle nearer than this and forward motion is cut.
    safety_stop_cm: float = 25.0
    #: Speed ceiling as a fraction of full scale.
    max_linear: float = 0.75
    max_angular: float = 0.65
    #: Forward speed retained during the hardest turn (0..1). Lower = the
    #: robot slows more to line itself up before driving on.
    cornering_speed_floor: float = 0.25
    #: Acceleration limits applied on top of the PIDs, per second.
    linear_slew_per_s: float = 1.2
    angular_slew_per_s: float = 2.5
    #: How long to coast after losing the target before searching.
    lost_coast_s: float = 0.8
    #: How long to search before giving up entirely.
    search_timeout_s: float = 8.0
    #: Yaw command used while sweeping for a lost target.
    search_angular: float = 0.35

    def __post_init__(self) -> None:
        if self.target_distance_cm <= self.safety_stop_cm:
            raise ValueError(
                "target_distance_cm must be greater than safety_stop_cm, otherwise the "
                "robot would be asked to hold a position inside its own stop distance."
            )
        if self.hold_band_cm <= 0 or self.max_linear <= 0 or self.max_angular <= 0:
            raise ValueError("hold_band_cm, max_linear and max_angular must be positive.")
        if self.range_scale_cm <= 0:
            raise ValueError("range_scale_cm must be positive.")


@dataclass
class DriveCommand:
    """What the follower wants the wheels to do this tick."""

    linear: float = 0.0
    angular: float = 0.0
    state: FollowState = FollowState.IDLE
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "linear": round(self.linear, 3),
            "angular": round(self.angular, 3),
            "state": self.state.value,
            "reason": self.reason,
        }


#: Gains tuned for a ~15 FPS camera loop on a small indoor differential base.
DEFAULT_BEARING_GAINS = PidGains(
    kp=0.85, ki=0.05, kd=0.12, output_limit=1.0, integral_limit=0.25,
    derivative_filter_s=0.10, deadband=0.05,
)
DEFAULT_RANGE_GAINS = PidGains(
    kp=1.30, ki=0.10, kd=0.15, output_limit=1.0, integral_limit=0.30,
    derivative_filter_s=0.15, deadband=0.02,
)


class PersonFollower:
    """Converts a visual target into smooth, safe drive commands."""

    def __init__(
        self,
        tuning: Optional[FollowTuning] = None,
        bearing_gains: PidGains = DEFAULT_BEARING_GAINS,
        range_gains: PidGains = DEFAULT_RANGE_GAINS,
    ) -> None:
        self.tuning = tuning or FollowTuning()
        self.bearing_pid = PidController(bearing_gains, name="bearing")
        self.range_pid = PidController(range_gains, name="range")
        self.state = FollowState.IDLE
        self._command = DriveCommand()
        self._holding = False
        self._lost_for_s = 0.0
        self._search_for_s = 0.0
        self._last_bearing_sign = 1.0

    # -- lifecycle --------------------------------------------------------
    def reset(self) -> None:
        """Drop all history. Call when following starts or stops."""
        self.bearing_pid.reset()
        self.range_pid.reset()
        self.state = FollowState.IDLE
        self._command = DriveCommand()
        self._holding = False
        self._lost_for_s = 0.0
        self._search_for_s = 0.0

    @property
    def command(self) -> DriveCommand:
        return self._command

    @property
    def gave_up(self) -> bool:
        """True once searching has run past ``search_timeout_s``."""
        return self._search_for_s >= self.tuning.search_timeout_s

    # -- the control step -------------------------------------------------
    def update(
        self,
        target: Optional[VisualTarget],
        dt: float,
        obstacle_cm: Optional[float] = None,
        search_when_lost: bool = True,
    ) -> DriveCommand:
        """Run one following step and return the drive command to apply."""
        if dt <= 0.0:
            return self._command

        if target is None:
            return self._handle_lost(dt, search_when_lost)

        self._lost_for_s = 0.0
        self._search_for_s = 0.0
        if target.bearing:
            self._last_bearing_sign = 1.0 if target.bearing > 0 else -1.0

        # Yaw: drive the person's bearing to the centre of the frame. With a
        # setpoint of zero the controller already produces the correcting
        # sign - a target to the right (+bearing) yields a negative yaw rate,
        # which is a turn to the right.
        angular = self.bearing_pid.update(setpoint=0.0, measurement=target.bearing, dt=dt)
        angular = clamp(angular, -self.tuning.max_angular, self.tuning.max_angular)

        distance_cm = target.distance_cm
        if distance_cm is None:
            # Bearing is still trustworthy without a range estimate, so keep
            # turning to face the person but do not drive blind.
            return self._finish(
                linear=0.0, angular=angular, dt=dt,
                state=FollowState.HOLDING, reason="no range estimate",
            )

        # Safety first: an obstacle inside the stop distance cuts forward
        # motion no matter what the range PID asks for.
        if obstacle_cm is not None and obstacle_cm <= self.tuning.safety_stop_cm:
            self.range_pid.reset()
            self._holding = True
            return self._finish(
                linear=0.0, angular=angular, dt=dt,
                state=FollowState.BLOCKED, reason=f"obstacle at {obstacle_cm:.0f}cm",
            )

        if self._should_hold(distance_cm):
            self.range_pid.reset()
            return self._finish(
                linear=0.0, angular=angular, dt=dt,
                state=FollowState.HOLDING, reason="within comfort band",
            )

        # Range: the measurement is the *shortfall* in distance, so the
        # error (setpoint 0 minus measurement) is positive exactly when the
        # person is further away than the hold distance - i.e. the PID output
        # is forward speed directly. Normalising by range_scale_cm keeps the
        # gains dimensionless and on the same scale as the bearing loop.
        range_error = (self.tuning.target_distance_cm - distance_cm) / self.tuning.range_scale_cm
        linear = self.range_pid.update(setpoint=0.0, measurement=range_error, dt=dt)
        # Forward-only chassis: closing in is the only motion available, so
        # "too close" becomes a stop rather than a reverse.
        linear = clamp(linear, 0.0, self.tuning.max_linear)
        linear *= self._cornering_scale(angular)

        return self._finish(
            linear=linear, angular=angular, dt=dt,
            state=FollowState.APPROACHING, reason=f"{distance_cm:.0f}cm to target",
        )

    # -- helpers ----------------------------------------------------------
    def _should_hold(self, distance_cm: float) -> bool:
        """Arrival test with hysteresis, so the robot does not creep.

        Two different thresholds are deliberate: the robot stops as soon as
        it reaches the comfort band, but only sets off again once the person
        has moved a clear ``resume_margin_cm`` beyond it.
        """
        stop_at = self.tuning.target_distance_cm + self.tuning.hold_band_cm
        resume_at = stop_at + self.tuning.resume_margin_cm
        if self._holding:
            if distance_cm > resume_at:
                self._holding = False
        elif distance_cm <= stop_at:
            self._holding = True
        return self._holding

    def _cornering_scale(self, angular: float) -> float:
        """Scale forward speed down as the yaw command grows."""
        turn_fraction = clamp(abs(angular) / self.tuning.max_angular, 0.0, 1.0)
        return map_range(turn_fraction, 0.0, 1.0, 1.0, self.tuning.cornering_speed_floor)

    def _handle_lost(self, dt: float, search_when_lost: bool) -> DriveCommand:
        """Coast, then optionally sweep in the direction the target left."""
        self._lost_for_s += dt
        if self._lost_for_s < self.tuning.lost_coast_s:
            return self._finish(
                linear=0.0, angular=self._command.angular * 0.5, dt=dt,
                state=FollowState.LOST, reason="target lost - coasting",
            )

        self.bearing_pid.reset()
        self.range_pid.reset()
        self._holding = False
        if not search_when_lost:
            return self._finish(linear=0.0, angular=0.0, dt=dt, state=FollowState.IDLE, reason="target lost")

        self._search_for_s += dt
        if self.gave_up:
            return self._finish(
                linear=0.0, angular=0.0, dt=dt,
                state=FollowState.IDLE, reason="search timed out",
            )
        # Sweep toward the side the person was last seen on - the most
        # likely place to find them again.
        sweep = -self.tuning.search_angular * self._last_bearing_sign
        return self._finish(
            linear=0.0, angular=sweep, dt=dt,
            state=FollowState.SEARCHING, reason="searching for target",
        )

    def _finish(
        self, linear: float, angular: float, dt: float, state: FollowState, reason: str
    ) -> DriveCommand:
        """Apply the acceleration limits and publish the command."""
        linear = slew(self._command.linear, clamp(linear, -self.tuning.max_linear, self.tuning.max_linear),
                      self.tuning.linear_slew_per_s * dt)
        angular = slew(self._command.angular, clamp(angular, -self.tuning.max_angular, self.tuning.max_angular),
                       self.tuning.angular_slew_per_s * dt)
        self.state = state
        self._command = DriveCommand(linear=linear, angular=angular, state=state, reason=reason)
        return self._command
