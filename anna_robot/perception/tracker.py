"""Keeps a stable lock on one target between detections.

Detection is the expensive part of the frame budget, so the robot runs it
every few frames. In between, and whenever a single frame misses, this
tracker carries the target forward: it matches each new detection to the one
it was already following, predicts where it went during the gap, and only
declares the target lost after a grace period.

The effect is a control loop that sees a continuous target instead of a
flickering one - which is what stops the wheels and the head twitching.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from ..utils import box_center, box_iou, clamp
from .object_detector import Detection

logger = logging.getLogger(__name__)


@dataclass
class Track:
    """The target currently being followed."""

    detection: Detection
    #: Pixels per second, estimated from consecutive detections.
    velocity: Tuple[float, float] = (0.0, 0.0)
    hits: int = 1
    misses: int = 0
    first_seen: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)

    @property
    def age_s(self) -> float:
        return max(time.monotonic() - self.first_seen, 0.0)

    @property
    def since_seen_s(self) -> float:
        return max(time.monotonic() - self.last_seen, 0.0)

    @property
    def box(self) -> Tuple[int, int, int, int]:
        return self.detection.box

    @property
    def center(self) -> Tuple[float, float]:
        return box_center(self.detection.box)

    def predict(self, dt: float, frame_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
        """Where the target probably is now, given its last known velocity."""
        width, height = frame_size
        vx, vy = self.velocity
        dx, dy = vx * dt, vy * dt
        xmin, ymin, xmax, ymax = self.detection.box
        return (
            int(clamp(xmin + dx, 0, width)),
            int(clamp(ymin + dy, 0, height)),
            int(clamp(xmax + dx, 0, width)),
            int(clamp(ymax + dy, 0, height)),
        )


class TargetTracker:
    """Single-target tracker with IoU + centre-distance matching.

    Single-target on purpose: ANNA interacts with one person at a time, and
    a full multi-object tracker would cost frame time to solve a problem she
    does not have.
    """

    def __init__(
        self,
        label: str = "person",
        iou_match_threshold: float = 0.25,
        max_center_jump_fraction: float = 0.45,
        confirm_hits: int = 2,
        max_misses: int = 8,
        max_coast_s: float = 1.2,
    ) -> None:
        self.label = label
        self.iou_match_threshold = float(iou_match_threshold)
        self.max_center_jump_fraction = float(max_center_jump_fraction)
        self.confirm_hits = int(confirm_hits)
        self.max_misses = int(max_misses)
        self.max_coast_s = float(max_coast_s)
        self._track: Optional[Track] = None

    # -- state ------------------------------------------------------------
    @property
    def track(self) -> Optional[Track]:
        return self._track

    @property
    def has_target(self) -> bool:
        return self._track is not None

    @property
    def is_confirmed(self) -> bool:
        """True once the target has been seen enough times to act on.

        This replaces the old free-running frame counter, which reset to
        zero on any single missed frame and made the robot flap between
        "person!" and "nobody".
        """
        return self._track is not None and self._track.hits >= self.confirm_hits

    def clear(self) -> None:
        self._track = None

    # -- update -----------------------------------------------------------
    def update(
        self, detections: Sequence[Detection], frame_size: Tuple[int, int], dt: float
    ) -> Optional[Track]:
        """Feed one frame of detections in; returns the current track."""
        candidates: List[Detection] = [d for d in detections if d.label == self.label]

        if self._track is None:
            best = self._pick_initial(candidates)
            if best is not None:
                self._track = Track(detection=best)
            return self._track

        match = self._match(self._track, candidates, frame_size)
        if match is not None:
            self._absorb(match, dt)
            return self._track

        # Nothing matched: coast on the last known velocity for a moment.
        self._track.misses += 1
        if self._track.misses > self.max_misses or self._track.since_seen_s > self.max_coast_s:
            logger.debug("Target lost after %d misses (%.2fs).", self._track.misses, self._track.since_seen_s)
            self._track = None
        return self._track

    def _pick_initial(self, candidates: Sequence[Detection]) -> Optional[Detection]:
        """Start on the nearest, most confident candidate."""
        if not candidates:
            return None
        return max(candidates, key=lambda d: d.area * (0.5 + d.score))

    def _match(
        self, track: Track, candidates: Sequence[Detection], frame_size: Tuple[int, int]
    ) -> Optional[Detection]:
        """Find the detection that is most plausibly the same target.

        Overlap alone fails when a fast walker's box does not touch its
        previous position, so the predicted box is matched first and a
        centre-distance gate catches the rest.
        """
        if not candidates:
            return None
        predicted = track.predict(track.since_seen_s, frame_size)
        width = max(frame_size[0], 1)
        max_jump = width * self.max_center_jump_fraction
        previous_center = box_center(predicted)

        scored = []
        for candidate in candidates:
            overlap = max(box_iou(candidate.box, track.box), box_iou(candidate.box, predicted))
            center = box_center(candidate.box)
            distance = ((center[0] - previous_center[0]) ** 2 + (center[1] - previous_center[1]) ** 2) ** 0.5
            if overlap < self.iou_match_threshold and distance > max_jump:
                continue
            # Prefer overlap, fall back to proximity.
            scored.append((overlap + (1.0 - min(distance / max_jump, 1.0)), candidate))
        if not scored:
            return None
        return max(scored, key=lambda pair: pair[0])[1]

    def _absorb(self, detection: Detection, dt: float) -> None:
        assert self._track is not None
        previous_center = self._track.center
        new_center = box_center(detection.box)
        elapsed = max(self._track.since_seen_s, dt, 1e-3)
        self._track.velocity = (
            (new_center[0] - previous_center[0]) / elapsed,
            (new_center[1] - previous_center[1]) / elapsed,
        )
        self._track.detection = detection
        self._track.hits += 1
        self._track.misses = 0
        self._track.last_seen = time.monotonic()
