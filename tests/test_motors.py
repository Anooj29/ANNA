"""Drive-base tests: mixing, ramping, stiction floor and the forward-only rule."""

from __future__ import annotations

import pytest

from anna_robot.motors import MotorController, MotorTuning

PINS = (17, 18, 22, 27)


def build(**kwargs) -> MotorController:
    return MotorController(*PINS, **kwargs)


# -- mixing -------------------------------------------------------------
def test_straight_ahead_drives_both_wheels_equally():
    assert MotorController.mix(1.0, 0.0) == (1.0, 1.0)


def test_positive_angular_turns_left():
    left, right = MotorController.mix(0.0, 1.0)
    assert left < right


def test_negative_angular_turns_right():
    left, right = MotorController.mix(0.0, -1.0)
    assert left > right


def test_mix_rescales_rather_than_clipping():
    """A hard turn keeps its shape instead of quietly straightening out."""
    left, right = MotorController.mix(1.0, 1.0)
    assert max(abs(left), abs(right)) == pytest.approx(1.0)
    assert left == pytest.approx(0.0)


# -- duty output --------------------------------------------------------
def test_stop_is_immediate_and_bypasses_the_ramp():
    motors = build()
    for _ in range(50):
        motors.drive(1.0, 0.0, dt=0.05)
    assert motors.is_moving
    motors.stop()
    assert motors.duties == (0.0, 0.0)


def test_drive_respects_the_duty_ceiling():
    motors = build(tuning=MotorTuning(min_duty=20, max_duty=60, ramp_duty_per_s=1000))
    for _ in range(20):
        left, right = motors.drive(1.0, 0.0, dt=0.05)
    assert left <= 60.0 and right <= 60.0


def test_tiny_commands_stop_rather_than_stall_the_motor():
    """Below the stiction floor a wheel only buzzes, so command a true stop."""
    motors = build()
    left, right = motors.drive(0.0001, 0.0, dt=1.0)
    assert (left, right) == (0.0, 0.0)


def test_acceleration_is_ramped():
    motors = build(tuning=MotorTuning(ramp_duty_per_s=100.0))
    first = motors.drive(1.0, 0.0, dt=0.1)[0]
    assert first <= 10.0 + 1e-6  # 100 duty/s * 0.1 s
    second = motors.drive(1.0, 0.0, dt=0.1)[0]
    assert second > first


def test_coast_ramps_down_to_zero():
    motors = build(tuning=MotorTuning(ramp_duty_per_s=200.0))
    for _ in range(40):
        motors.drive(1.0, 0.0, dt=0.05)
    motors.coast(dt=0.05)
    assert 0 < motors.duties[0] < 75.0
    for _ in range(40):
        motors.coast(dt=0.05)
    assert motors.duties == (0.0, 0.0)


def test_forward_only_wiring_refuses_reverse(simulated_gpio):
    motors = build(allow_reverse=False)
    for _ in range(40):
        motors.drive(-1.0, 0.0, dt=0.05)
    assert motors.duties == (0.0, 0.0)
    assert simulated_gpio.outputs[PINS[0]] == 0  # Direction pin never flipped.


def test_a_pivot_turn_drives_only_one_wheel_on_forward_only_wiring():
    motors = build(tuning=MotorTuning(ramp_duty_per_s=1000))
    for _ in range(20):
        left, right = motors.drive(0.0, 1.0, dt=0.05)
    assert left == 0.0 and right > 0.0


# -- original fixed-speed API ------------------------------------------
def test_legacy_helpers_keep_their_original_duties():
    motors = build()
    motors.forward()
    assert motors.duties == (50.0, 50.0)
    motors.turn_left()
    assert motors.duties == (25.0, 50.0)
    motors.turn_right()
    assert motors.duties == (50.0, 25.0)
    motors.stop()
    assert motors.duties == (0.0, 0.0)


def test_close_stops_the_pwm_channels():
    motors = build()
    motors.forward()
    motors.close()
    assert motors.duties == (0.0, 0.0)
    motors.drive(1.0, 0.0, dt=0.1)  # Safe to call after closing.
    assert motors.duties == (0.0, 0.0)


def test_tuning_rejects_an_inverted_duty_band():
    with pytest.raises(ValueError, match="min_duty"):
        MotorTuning(min_duty=80, max_duty=20)
