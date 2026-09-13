"""Head-tracking tests, with the servo travel limits as the headline case.

The head carries the camera cabling, so "the head can never wind past its
limit" is a safety property, not a nicety. These tests pin it down from
several directions: configuration, direct commands, and a PID that is
actively trying to push further.
"""

from __future__ import annotations

import pytest

from anna_robot.control.visual import VisualFeedback
from anna_robot.hardware.servo import (
    ABSOLUTE_MAX_ANGLE_DEG,
    ABSOLUTE_MIN_ANGLE_DEG,
    Servo,
    ServoLimits,
)
from anna_robot.head_tracker import HeadState, HeadTracker

FRAME = (640, 480)


def track_for(head: HeadTracker, box, seconds: float = 6.0, dt: float = 0.05):
    """Feed one fixed target in for a while and return the final angles."""
    feedback = VisualFeedback(smoothing_s=0.05)
    for _ in range(int(seconds / dt)):
        target = feedback.update(box, FRAME, dt, score=0.9)
        head.update(target, dt)
    return head.angles


# -- configuration guards ----------------------------------------------
def test_limits_reject_full_rotation():
    with pytest.raises(ValueError, match="safe range"):
        ServoLimits(-180.0, 180.0)
    with pytest.raises(ValueError, match="safe range"):
        ServoLimits(-90.1, 90.1)


def test_limits_reject_inverted_and_bad_values():
    with pytest.raises(ValueError, match="below max angle"):
        ServoLimits(50.0, -50.0)
    with pytest.raises(ValueError, match="max speed"):
        ServoLimits(-40.0, 40.0, max_speed_deg_s=0.0)
    with pytest.raises(ValueError, match="centre"):
        ServoLimits(-40.0, 40.0, center_deg=60.0)


def test_absolute_range_is_a_half_turn_at_most():
    assert ABSOLUTE_MAX_ANGLE_DEG - ABSOLUTE_MIN_ANGLE_DEG <= 180.0


# -- servo clamping -----------------------------------------------------
def test_servo_clamps_commands_beyond_travel():
    servo = Servo(12, ServoLimits(-70.0, 70.0))
    assert servo.command(1000.0) == 70.0
    assert servo.command(-1000.0) == -70.0


def test_servo_never_exceeds_limits_while_slewing():
    servo = Servo(12, ServoLimits(-45.0, 45.0, max_speed_deg_s=500.0))
    servo.command(360.0)
    for _ in range(100):
        angle = servo.update(0.1)
        assert -45.0 <= angle <= 45.0


def test_servo_nudge_is_also_clamped():
    servo = Servo(12, ServoLimits(-30.0, 30.0))
    for _ in range(50):
        servo.nudge(10.0)
    assert servo.target == 30.0


def test_servo_duty_stays_within_pwm_range(simulated_gpio):
    servo = Servo(12, ServoLimits(-70.0, 70.0, max_speed_deg_s=1000.0))
    for angle in (-70.0, 0.0, 70.0):
        servo.command(angle)
        servo.update(1.0)
        assert 0.0 <= simulated_gpio.pwm_duty[12] <= 100.0


# -- tracking behaviour --------------------------------------------------
def test_head_pans_toward_a_target_on_the_right():
    head = HeadTracker(pan_pin=12, tilt_pin=13)
    pan, _ = track_for(head, (560, 200, 640, 400), seconds=2.0)
    assert pan < -5.0  # Positive pan is left, so a right-hand target pans negative.


def test_head_pans_toward_a_target_on_the_left():
    head = HeadTracker(pan_pin=12, tilt_pin=13)
    pan, _ = track_for(head, (0, 200, 80, 400), seconds=2.0)
    assert pan > 5.0


def test_head_stops_at_the_limit_however_long_it_tracks():
    """The PID keeps demanding more pan; the head must not give it."""
    head = HeadTracker(pan_pin=12, tilt_pin=13)
    pan, tilt = track_for(head, (630, 460, 640, 480), seconds=30.0)
    assert pan == pytest.approx(head.pan_limits.min_angle_deg)
    assert head.pan_limits.min_angle_deg <= pan <= head.pan_limits.max_angle_deg
    assert head.tilt_limits.min_angle_deg <= tilt <= head.tilt_limits.max_angle_deg
    assert head.at_limit is True
    assert head.state is HeadState.AT_LIMIT


def test_head_holds_still_inside_the_deadband():
    head = HeadTracker(pan_pin=12, tilt_pin=13)
    centred = (300, 180, 340, 300)
    pan_before, _ = track_for(head, centred, seconds=1.0)
    pan_after, _ = track_for(head, centred, seconds=2.0)
    assert abs(pan_after - pan_before) < 2.0


def test_head_recenters_after_losing_the_target():
    head = HeadTracker(pan_pin=12, tilt_pin=13)
    track_for(head, (600, 200, 640, 400), seconds=2.0)
    assert abs(head.angles[0]) > 5.0
    for _ in range(300):  # 15 s with nothing in view
        head.update(None, 0.05)
    assert head.angles[0] == pytest.approx(0.0, abs=1.0)
    assert head.state is HeadState.CENTERED


def test_look_at_is_clamped_too():
    head = HeadTracker(pan_pin=12, tilt_pin=13)
    pan, tilt = head.look_at(500.0, -500.0)
    assert pan == head.pan_limits.max_angle_deg
    assert tilt == head.tilt_limits.min_angle_deg


def test_disabled_head_is_safe_to_call():
    head = HeadTracker(pan_pin=None, tilt_pin=None)
    assert head.enabled is False
    assert head.update(None, 0.05) == (0.0, 0.0)
    head.center()
    head.nod()
    assert head.as_dict()["enabled"] is False


def test_head_status_reports_its_limits():
    head = HeadTracker(pan_pin=12, tilt_pin=13)
    status = head.as_dict()
    assert status["pan_min_deg"] == -70.0
    assert status["pan_max_deg"] == 70.0
    assert status["tilt_min_deg"] == -30.0
