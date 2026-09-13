"""The feedback contract shared by every sensing modality.

ANNA closes its loops on vision today. Wheel encoders and an IMU are planned
but not fitted, so rather than hard-wiring the camera into the controllers,
each modality implements :class:`FeedbackSource` and is registered with a
:class:`FeedbackBus`. Adding encoders later is then a matter of enabling the
existing source - no controller has to change.

Each source reports a :class:`MotionEstimate`; the bus picks the most
trustworthy estimate available (highest confidence among fresh sources), so
a modality that drops out simply stops being selected.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class MotionEstimate:
    """One modality's view of how the robot is moving, in robot frame.

    Any field may be ``None`` when the modality cannot observe it: a camera
    sees bearing but not wheel slip, encoders see travel but not heading
    drift, an IMU sees rotation but not position.
    """

    #: Forward speed, m/s. Positive is forward.
    linear_velocity_mps: Optional[float] = None
    #: Yaw rate, rad/s. Positive is counter-clockwise (left).
    angular_velocity_rps: Optional[float] = None
    #: Heading relative to where the source was last reset, radians.
    heading_rad: Optional[float] = None
    #: Distance travelled since the last reset, metres.
    distance_m: Optional[float] = None
    #: 0.0 (useless) to 1.0 (fully trusted).
    confidence: float = 0.0
    #: ``time.monotonic()`` when the estimate was produced.
    timestamp: float = field(default_factory=time.monotonic)

    @property
    def age_s(self) -> float:
        return max(time.monotonic() - self.timestamp, 0.0)

    def is_fresh(self, max_age_s: float) -> bool:
        return self.confidence > 0.0 and self.age_s <= max_age_s

    def as_dict(self) -> Dict[str, object]:
        return {
            "linear_mps": None if self.linear_velocity_mps is None else round(self.linear_velocity_mps, 3),
            "angular_rps": None if self.angular_velocity_rps is None else round(self.angular_velocity_rps, 3),
            "heading_rad": None if self.heading_rad is None else round(self.heading_rad, 3),
            "distance_m": None if self.distance_m is None else round(self.distance_m, 3),
            "confidence": round(self.confidence, 2),
            "age_s": round(self.age_s, 2),
        }


@runtime_checkable
class FeedbackSource(Protocol):
    """Anything that can tell the control loop how the robot is moving."""

    name: str
    enabled: bool

    def poll(self) -> MotionEstimate:
        """Return the latest estimate. Must not block the control loop."""

    def reset(self) -> None:
        """Zero any accumulated state (heading, odometry)."""

    def close(self) -> None:
        """Release hardware resources."""


class BaseFeedbackSource:
    """Shared plumbing for feedback sources (name, enable flag, no-op close)."""

    def __init__(self, name: str, enabled: bool = True) -> None:
        self.name = name
        self.enabled = bool(enabled)
        self._last = MotionEstimate(confidence=0.0)

    @property
    def last_estimate(self) -> MotionEstimate:
        return self._last

    def poll(self) -> MotionEstimate:  # pragma: no cover - overridden
        return self._last

    def reset(self) -> None:
        self._last = MotionEstimate(confidence=0.0)

    def close(self) -> None:
        """Nothing to release by default."""


class FeedbackBus:
    """Collects every feedback source and exposes the best current estimate."""

    def __init__(self, sources: Iterable[FeedbackSource] = (), max_age_s: float = 0.5) -> None:
        self._sources: List[FeedbackSource] = list(sources)
        self.max_age_s = float(max_age_s)
        self._estimates: Dict[str, MotionEstimate] = {}

    def add(self, source: FeedbackSource) -> FeedbackSource:
        self._sources.append(source)
        logger.info(
            "Feedback source '%s' registered (%s).",
            source.name,
            "enabled" if source.enabled else "disabled - reserved for future hardware",
        )
        return source

    @property
    def sources(self) -> List[FeedbackSource]:
        return list(self._sources)

    def get(self, name: str) -> Optional[FeedbackSource]:
        return next((source for source in self._sources if source.name == name), None)

    def poll(self) -> Dict[str, MotionEstimate]:
        """Poll every enabled source once. Never raises: a broken sensor
        must not be able to stop the control loop."""
        estimates: Dict[str, MotionEstimate] = {}
        for source in self._sources:
            if not source.enabled:
                continue
            try:
                estimates[source.name] = source.poll()
            except Exception:
                logger.exception("Feedback source '%s' failed; ignoring it this tick.", source.name)
        self._estimates = estimates
        return estimates

    def best(self) -> Optional[MotionEstimate]:
        """Highest-confidence fresh estimate, or None if nothing is usable."""
        fresh = [e for e in self._estimates.values() if e.is_fresh(self.max_age_s)]
        return max(fresh, key=lambda e: e.confidence, default=None)

    def reset(self) -> None:
        for source in self._sources:
            try:
                source.reset()
            except Exception:
                logger.exception("Feedback source '%s' failed to reset.", source.name)

    def close(self) -> None:
        for source in self._sources:
            try:
                source.close()
            except Exception:
                logger.exception("Feedback source '%s' failed to close.", source.name)

    def as_dict(self) -> Dict[str, object]:
        return {name: estimate.as_dict() for name, estimate in self._estimates.items()}
