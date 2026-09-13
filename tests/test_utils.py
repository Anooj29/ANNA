"""Tests for the shared scalar maths helpers."""

from __future__ import annotations

import pytest

from anna_robot.utils import (
    Deadline,
    ExponentialFilter,
    RateLimiter,
    box_iou,
    clamp,
    clean_text,
    deadband,
    lerp,
    map_range,
    slew,
)


def test_clamp_handles_swapped_bounds():
    assert clamp(5, 0, 1) == 1
    assert clamp(-5, 0, 1) == 0
    # A swapped pair must still produce a bounded result, never an unbounded one.
    assert clamp(5, 1, 0) == 1


def test_deadband_is_continuous_at_the_edge():
    assert deadband(0.05, 0.1) == 0.0
    assert deadband(-0.05, 0.1) == 0.0
    assert deadband(0.1000001, 0.1) == pytest.approx(0.0, abs=1e-6)
    assert deadband(0.3, 0.1) == pytest.approx(0.2)
    assert deadband(-0.3, 0.1) == pytest.approx(-0.2)
    assert deadband(5.0, 0.0) == 5.0


def test_slew_limits_step_size():
    assert slew(0.0, 1.0, 0.25) == 0.25
    assert slew(1.0, 0.0, 0.25) == 0.75
    assert slew(0.0, 0.1, 0.25) == 0.1
    assert slew(0.0, 1.0, 0.0) == 1.0  # No limit means jump straight there.


def test_map_range_clamps_to_output():
    assert map_range(0.5, 0, 1, 0, 10) == pytest.approx(5.0)
    assert map_range(2.0, 0, 1, 0, 10) == 10
    assert map_range(1.0, 0, 0, 3, 9) == 3  # Degenerate input range.


def test_lerp():
    assert lerp(0, 10, 0.25) == pytest.approx(2.5)
    assert lerp(0, 10, 5) == 10


def test_exponential_filter_converges_and_is_rate_independent():
    fast = ExponentialFilter(0.2, initial=0.0)
    for _ in range(100):
        fast.update(1.0, 0.02)
    slow = ExponentialFilter(0.2, initial=0.0)
    for _ in range(20):
        slow.update(1.0, 0.1)
    # Same two seconds of real time either way, so the same answer.
    assert fast.value == pytest.approx(slow.value, abs=0.02)
    assert fast.value == pytest.approx(1.0, abs=0.01)


def test_rate_limiter():
    limiter = RateLimiter(1.0)
    assert limiter.trigger(now=100.0) is True
    assert limiter.trigger(now=100.5) is False
    assert limiter.trigger(now=101.0) is True


def test_deadline_is_non_blocking():
    deadline = Deadline()
    assert deadline.expired() is True  # Unarmed deadlines never hold anything up.
    deadline.arm(10.0, now=100.0)
    assert deadline.expired(now=105.0) is False
    assert deadline.remaining(now=105.0) == pytest.approx(5.0)
    assert deadline.expired(now=110.0) is True
    deadline.clear()
    assert deadline.armed is False


def test_box_iou():
    assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert box_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert box_iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)


def test_clean_text_strips_markdown_and_non_ascii():
    assert clean_text("**Hello** — there\nfriend") == "Hello there friend"
    assert clean_text("") == ""
