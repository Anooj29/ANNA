"""Visual feedback: what the camera can tell the control loop.

This is ANNA's only *active* feedback modality today. It converts a target
bounding box into two normalised errors the PIDs can close on:

* **bearing** - how far left/right of centre the target sits, as -1..+1
  across the frame. Independent of resolution, so retuning is not needed if
  the camera mode changes.
* **range** - distance to the target. The ultrasonic sensor is used when it
  has a plausible reading, and the target's apparent height in the frame is
  the fallback (and cross-check), because the ultrasonic beam is narrow and
  misses a person who is off to one side.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from ..utils import ExponentialFilter, clamp
from .feedback import BaseFeedbackSource, MotionEstimate

logger = logging.getLogger(__name__)


@dataclass
class VisualTarget:
    """A target as the controllers see it, in normalised units."""

    #: -1.0 (far left) .. +1.0 (far right) of the frame.
    bearing: float
    #: -1.0 (top) .. +1.0 (bottom) of the frame.
    elevation: float
    #: Estimated distance in cm, or None if unknown.
    distance_cm: Optional[float]
    #: Fraction of frame height occupied by the target, 0..1.
    height_fraction: float
    #: Detection confidence, 0..1.
    score: float
    #: Pixel centre, kept for the head tracker and the debug overlay.
    center_px: Tuple[float, float]
    box: Tuple[int, int, int, int]
    timestamp: float

    @property
    def age_s(self) -> float:
        return max(time.monotonic() - self.timestamp, 0.0)

    def as_dict(self) -> dict:
        return {
            "bearing": round(self.bearing, 3),
            "elevation": round(self.elevation, 3),
            "distance_cm": None if self.distance_cm is None else round(self.distance_cm, 1),
            "height_fraction": round(self.height_fraction, 3),
            "score": round(self.score, 3),
        }


class VisualFeedback(BaseFeedbackSource):
    """Turns detections into smoothed, controller-ready visual errors.

    Smoothing happens here rather than in the PIDs so that every consumer
    (drive follower, head tracker, telemetry) sees the same filtered target,
    and so a single dropped detection does not yank the wheels.
    """

    #: Rough average standing height of an adult, used by the monocular
    #: range estimate. Only ever a coarse estimate - the ultrasonic reading
    #: wins whenever it is available.
    ASSUMED_PERSON_HEIGHT_CM = 170.0

    def __init__(
        self,
        smoothing_s: float = 0.12,
        target_timeout_s: float = 1.0,
        vertical_fov_deg: float = 48.0,
        enabled: bool = True,
    ) -> None:
        super().__init__(name="visual", enabled=enabled)
        self.target_timeout_s = float(target_timeout_s)
        self._bearing = ExponentialFilter(smoothing_s)
        self._elevation = ExponentialFilter(smoothing_s)
        self._distance = ExponentialFilter(max(smoothing_s * 2.0, 0.05))
        self._target: Optional[VisualTarget] = None
        self._last_seen: Optional[float] = None
        # Pinhole constant: apparent height fraction -> distance.
        self._focal_constant = self.ASSUMED_PERSON_HEIGHT_CM / (
            2.0 * math.tan(math.radians(vertical_fov_deg) / 2.0)
        )

    # -- estimation -------------------------------------------------------
    def estimate_distance_cm(self, height_fraction: float) -> Optional[float]:
        """Monocular range from apparent height (fallback for the sonar)."""
        if height_fraction <= 0.01:
            return None
        return self._focal_constant / height_fraction

    def update(
        self,
        box: Optional[Tuple[int, int, int, int]],
        frame_size: Tuple[int, int],
        dt: float,
        score: float = 0.0,
        sonar_distance_cm: Optional[float] = None,
    ) -> Optional[VisualTarget]:
        """Feed one frame's detection in and get the smoothed target back.

        Pass ``box=None`` when nothing was detected: the target is held for
        ``target_timeout_s`` so a momentary miss does not look like a loss.
        """
        now = time.monotonic()
        width, height = frame_size
        if box is None or width <= 0 or height <= 0:
            if self._last_seen is not None and (now - self._last_seen) > self.target_timeout_s:
                self.clear()
            return self._target

        xmin, ymin, xmax, ymax = box
        center_x = (xmin + xmax) / 2.0
        center_y = (ymin + ymax) / 2.0
        # Normalise to -1..+1 so gains stay valid at any resolution.
        bearing = clamp((center_x - width / 2.0) / (width / 2.0), -1.0, 1.0)
        elevation = clamp((center_y - height / 2.0) / (height / 2.0), -1.0, 1.0)
        height_fraction = clamp((ymax - ymin) / float(height), 0.0, 1.0)

        visual_distance = self.estimate_distance_cm(height_fraction)
        distance_cm = self._choose_distance(sonar_distance_cm, visual_distance)

        smooth_bearing = self._bearing.update(bearing, dt)
        smooth_elevation = self._elevation.update(elevation, dt)
        smooth_distance = None if distance_cm is None else self._distance.update(distance_cm, dt)

        self._last_seen = now
        self._target = VisualTarget(
            bearing=smooth_bearing,
            elevation=smooth_elevation,
            distance_cm=smooth_distance,
            height_fraction=height_fraction,
            score=float(score),
            center_px=(center_x, center_y),
            box=(int(xmin), int(ymin), int(xmax), int(ymax)),
            timestamp=now,
        )
        return self._target

    @staticmethod
    def _choose_distance(sonar_cm: Optional[float], visual_cm: Optional[float]) -> Optional[float]:
        """Prefer the sonar, but only while it is reporting something sane.

        The HC-SR04 returns its no-echo sentinel when the person is off-axis
        or the beam hits a soft surface; in those frames the monocular
        estimate is the better of two imperfect numbers.
        """
        sonar_usable = sonar_cm is not None and 2.0 < sonar_cm < 400.0
        if sonar_usable:
            return sonar_cm
        return visual_cm

    # -- accessors --------------------------------------------------------
    @property
    def target(self) -> Optional[VisualTarget]:
        return self._target

    @property
    def has_target(self) -> bool:
        return self._target is not None

    def seconds_since_seen(self) -> float:
        if self._last_seen is None:
            return float("inf")
        return max(time.monotonic() - self._last_seen, 0.0)

    def clear(self) -> None:
        """Forget the target (call on target loss or a state change)."""
        self._target = None
        self._last_seen = None
        self._bearing.reset()
        self._elevation.reset()
        self._distance.reset()

    # -- FeedbackSource ---------------------------------------------------
    def poll(self) -> MotionEstimate:
        """Report bearing-derived confidence for the feedback bus.

        A camera cannot measure the robot's own velocity, so only confidence
        and freshness are published; the follower reads :attr:`target`
        directly for the values it needs.
        """
        target = self._target
        if target is None:
            self._last = MotionEstimate(confidence=0.0)
            return self._last
        # Confidence decays as the detection ages so stale targets lose to
        # any fresher modality that comes online later.
        freshness = clamp(1.0 - target.age_s / max(self.target_timeout_s, 1e-6), 0.0, 1.0)
        self._last = MotionEstimate(
            confidence=clamp(target.score * freshness, 0.0, 1.0),
            timestamp=target.timestamp,
        )
        return self._last

    def reset(self) -> None:
        super().reset()
        self.clear()
