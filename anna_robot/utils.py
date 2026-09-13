"""Small shared helpers: text clean-up, scalar math and rate limiting.

Everything here is pure Python (no numpy, no hardware), so it can be unit
tested on any machine and imported from any module without cost.
"""

from __future__ import annotations

import re
import time
from typing import Optional, Tuple

_MARKDOWN_EMPHASIS = re.compile(r"[*_`#]+")
_NON_ASCII = re.compile(r"[^\x00-\x7F]")
_WHITESPACE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Strip markdown emphasis and non-ASCII characters so the TTS engine
    doesn't choke on emoji / accented characters returned by the LLM."""
    if not text:
        return ""
    text = _MARKDOWN_EMPHASIS.sub("", text)
    text = _NON_ASCII.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def clamp(value: float, lowest: float, highest: float) -> float:
    """Constrain ``value`` to ``[lowest, highest]``.

    The bounds are ordered defensively so a swapped pair (a classic
    configuration typo) can never turn into an unbounded actuator command.
    """
    if lowest > highest:
        lowest, highest = highest, lowest
    return lowest if value < lowest else highest if value > highest else value


def deadband(value: float, threshold: float) -> float:
    """Return 0 for small inputs, otherwise ``value`` shifted toward zero.

    Re-scaling (rather than simply zeroing) keeps the response continuous at
    the edge of the band, which is what stops a servo or wheel from snapping
    as the error crosses the threshold.
    """
    threshold = abs(threshold)
    if threshold <= 0.0:
        return value
    if abs(value) <= threshold:
        return 0.0
    return value - threshold if value > 0.0 else value + threshold


def slew(current: float, target: float, max_delta: float) -> float:
    """Move ``current`` toward ``target`` by at most ``max_delta``."""
    if max_delta <= 0.0:
        return target
    delta = clamp(target - current, -max_delta, max_delta)
    return current + delta


def lerp(start: float, end: float, fraction: float) -> float:
    """Linear interpolation with ``fraction`` clamped to ``[0, 1]``."""
    return start + (end - start) * clamp(fraction, 0.0, 1.0)


def map_range(
    value: float,
    in_low: float,
    in_high: float,
    out_low: float,
    out_high: float,
) -> float:
    """Rescale ``value`` from one range to another, clamped to the output."""
    if in_high == in_low:
        return out_low
    fraction = (value - in_low) / (in_high - in_low)
    return clamp(out_low + fraction * (out_high - out_low), out_low, out_high)


class ExponentialFilter:
    """First-order low-pass filter (EMA) with a time-constant in seconds.

    Framing the smoothing as a time constant rather than a bare alpha keeps
    the behaviour identical whether the loop runs at 5 or 30 FPS, which
    matters because the vision pipeline's rate varies with scene content.
    """

    def __init__(self, time_constant_s: float, initial: Optional[float] = None) -> None:
        self.time_constant_s = max(float(time_constant_s), 0.0)
        self._value = initial

    @property
    def value(self) -> Optional[float]:
        return self._value

    def reset(self, value: Optional[float] = None) -> None:
        self._value = value

    def update(self, sample: float, dt: float) -> float:
        sample = float(sample)
        if self._value is None or dt <= 0.0 or self.time_constant_s <= 0.0:
            self._value = sample
            return self._value
        alpha = dt / (self.time_constant_s + dt)
        self._value += alpha * (sample - self._value)
        return self._value


class RateLimiter:
    """Allows an action at most once every ``interval_s`` seconds."""

    def __init__(self, interval_s: float) -> None:
        self.interval_s = max(float(interval_s), 0.0)
        self._last: Optional[float] = None

    def ready(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        return self._last is None or (now - self._last) >= self.interval_s

    def trigger(self, now: Optional[float] = None) -> bool:
        """Return True (and start a new interval) if the action may run."""
        now = time.monotonic() if now is None else now
        if self.ready(now):
            self._last = now
            return True
        return False

    def reset(self) -> None:
        self._last = None


class LoopTimer:
    """Measures loop period/FPS and paces the loop to a target rate.

    ``sleep_to_rate`` gives back CPU time the control loop does not need,
    which on a Pi is the difference between a responsive robot and one whose
    perception threads are starved by a spinning main loop.
    """

    def __init__(self, target_fps: float = 0.0, smoothing_s: float = 1.0) -> None:
        self.target_period_s = 1.0 / target_fps if target_fps > 0 else 0.0
        self._filter = ExponentialFilter(smoothing_s)
        self._last_tick: Optional[float] = None
        self._last_sleep_end: Optional[float] = None

    def tick(self, now: Optional[float] = None) -> float:
        """Record one iteration and return the elapsed time since the last."""
        now = time.monotonic() if now is None else now
        dt = 0.0 if self._last_tick is None else now - self._last_tick
        self._last_tick = now
        if dt > 0.0:
            self._filter.update(dt, dt)
        return dt

    @property
    def fps(self) -> float:
        period = self._filter.value
        return 1.0 / period if period else 0.0

    def sleep_to_rate(self) -> None:
        """Sleep just long enough to hold the configured target rate."""
        if self.target_period_s <= 0.0:
            return
        now = time.monotonic()
        if self._last_sleep_end is not None:
            remaining = self.target_period_s - (now - self._last_sleep_end)
            if remaining > 0.0:
                time.sleep(remaining)
        self._last_sleep_end = time.monotonic()


class Deadline:
    """A non-blocking replacement for ``time.sleep`` inside a control loop.

    The state machine arms a deadline and keeps running; sleeping instead
    would freeze obstacle sensing, head tracking and telemetry along with it.
    """

    def __init__(self) -> None:
        self._expires_at: Optional[float] = None

    def arm(self, seconds: float, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        self._expires_at = now + max(float(seconds), 0.0)

    def clear(self) -> None:
        self._expires_at = None

    @property
    def armed(self) -> bool:
        return self._expires_at is not None

    def expired(self, now: Optional[float] = None) -> bool:
        if self._expires_at is None:
            return True
        now = time.monotonic() if now is None else now
        return now >= self._expires_at

    def remaining(self, now: Optional[float] = None) -> float:
        if self._expires_at is None:
            return 0.0
        now = time.monotonic() if now is None else now
        return max(self._expires_at - now, 0.0)


def box_center(box: Tuple[int, int, int, int]) -> Tuple[float, float]:
    """Centre (x, y) of an ``(xmin, ymin, xmax, ymax)`` box."""
    xmin, ymin, xmax, ymax = box
    return (xmin + xmax) / 2.0, (ymin + ymax) / 2.0


def box_area(box: Tuple[int, int, int, int]) -> float:
    xmin, ymin, xmax, ymax = box
    return max(xmax - xmin, 0) * max(ymax - ymin, 0)


def box_iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    """Intersection-over-union of two boxes; 0.0 when they do not overlap."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_w = min(ax2, bx2) - max(ax1, bx1)
    inter_h = min(ay2, by2) - max(ay1, by1)
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    intersection = float(inter_w * inter_h)
    union = box_area(a) + box_area(b) - intersection
    return intersection / union if union > 0 else 0.0
