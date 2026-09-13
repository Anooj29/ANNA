"""Tests for the PID controller - the piece every control loop depends on."""

from __future__ import annotations

import pytest

from anna_robot.control.pid import PidController, PidGains


def simulate(pid: PidController, setpoint: float, steps: int = 400, dt: float = 0.02, gain: float = 2.0):
    """Run the controller against a simple first-order plant."""
    measurement = 0.0
    history = []
    for _ in range(steps):
        output = pid.update(setpoint, measurement, dt)
        measurement += output * gain * dt
        history.append(measurement)
    return measurement, history


def test_pi_controller_reaches_setpoint():
    pid = PidController(PidGains(kp=0.8, ki=0.5, kd=0.05, output_limit=1.0))
    final, _ = simulate(pid, 1.0)
    assert final == pytest.approx(1.0, abs=0.02)


def test_output_is_clamped_to_the_limit():
    pid = PidController(PidGains(kp=10.0, output_limit=0.4))
    assert pid.update(1.0, 0.0, 0.02) == pytest.approx(0.4)
    assert pid.update(-1.0, 0.0, 0.02) == pytest.approx(-0.4)


def test_integral_cannot_wind_up_against_a_blocked_plant():
    """A robot held against a wall must not store up a lurch."""
    pid = PidController(PidGains(kp=1.0, ki=5.0, output_limit=0.5, integral_limit=0.2))
    for _ in range(500):
        pid.update(1.0, 0.0, 0.02)  # Measurement never moves.
    assert abs(pid.integral) <= 0.2
    assert abs(pid.update(1.0, 0.0, 0.02)) <= 0.5


def test_integral_recovers_once_out_of_saturation():
    pid = PidController(PidGains(kp=0.2, ki=1.0, output_limit=1.0, integral_limit=0.5))
    for _ in range(50):
        pid.update(1.0, 0.9, 0.02)
    assert pid.integral > 0.0


def test_derivative_on_measurement_avoids_a_setpoint_kick():
    """Changing the target must not produce a derivative spike."""
    pid = PidController(PidGains(kp=1.0, kd=5.0, output_limit=100.0, derivative_filter_s=0.0))
    for _ in range(5):
        pid.update(0.0, 0.0, 0.02)
    output = pid.update(10.0, 0.0, 0.02)
    assert output == pytest.approx(10.0)  # Proportional only; no D kick.


def test_derivative_opposes_measurement_change():
    pid = PidController(PidGains(kp=0.0, kd=1.0, output_limit=100.0, derivative_filter_s=0.0))
    pid.update(0.0, 0.0, 0.1)
    assert pid.update(0.0, 1.0, 0.1) < 0.0  # Rising measurement -> negative D.


def test_deadband_suppresses_tiny_errors():
    pid = PidController(PidGains(kp=1.0, deadband=0.1, output_limit=1.0))
    assert pid.update(0.05, 0.0, 0.02) == 0.0
    assert pid.update(0.5, 0.0, 0.02) == pytest.approx(0.4)


def test_reset_clears_history():
    pid = PidController(PidGains(kp=1.0, ki=1.0, output_limit=1.0))
    for _ in range(20):
        pid.update(1.0, 0.0, 0.02)
    pid.reset()
    assert pid.integral == 0.0
    assert pid.debug.output == 0.0


def test_zero_dt_is_a_no_op():
    pid = PidController(PidGains(kp=1.0))
    assert pid.update(1.0, 0.0, 0.0) == 0.0


def test_gains_scale():
    scaled = PidGains(kp=1.0, ki=2.0, kd=3.0).scaled(0.5)
    assert (scaled.kp, scaled.ki, scaled.kd) == (0.5, 1.0, 1.5)
