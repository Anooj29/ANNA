"""Tests for the feedback segments: visual (active), encoder and IMU (future)."""

from __future__ import annotations

import math

import pytest

from anna_robot.control.encoder import EncoderGeometry, WheelEncoderFeedback
from anna_robot.control.feedback import FeedbackBus, MotionEstimate
from anna_robot.control.imu import ImuFeedback, SimulatedImuReader
from anna_robot.control.visual import VisualFeedback

FRAME = (640, 480)


# -- visual --------------------------------------------------------------
def test_bearing_is_normalised_across_the_frame():
    feedback = VisualFeedback(smoothing_s=0.0)
    centred = feedback.update((300, 100, 340, 400), FRAME, 0.05, score=0.9)
    assert centred.bearing == pytest.approx(0.0, abs=0.05)
    right = feedback.update((600, 100, 640, 400), FRAME, 0.05, score=0.9)
    assert right.bearing > 0.8
    feedback.clear()
    left = feedback.update((0, 100, 40, 400), FRAME, 0.05, score=0.9)
    assert left.bearing < -0.8


def test_bearing_is_resolution_independent():
    """Gains must stay valid if the camera mode changes."""
    small = VisualFeedback(smoothing_s=0.0).update((240, 50, 280, 200), (320, 240), 0.05)
    large = VisualFeedback(smoothing_s=0.0).update((960, 200, 1120, 800), (1280, 960), 0.05)
    assert small.bearing == pytest.approx(large.bearing, abs=0.05)


def test_the_sonar_reading_is_preferred_when_plausible():
    feedback = VisualFeedback(smoothing_s=0.0)
    feedback._distance.time_constant_s = 0.0
    target = feedback.update((300, 100, 340, 400), FRAME, 0.05, sonar_distance_cm=75.0)
    assert target.distance_cm == pytest.approx(75.0)


def test_the_no_echo_sentinel_falls_back_to_the_visual_estimate():
    """The sonar beam is narrow; an off-axis person reads as 'nothing'."""
    feedback = VisualFeedback(smoothing_s=0.0)
    feedback._distance.time_constant_s = 0.0
    target = feedback.update((300, 100, 340, 400), FRAME, 0.05, sonar_distance_cm=999.0)
    assert 0 < target.distance_cm < 999.0


def test_a_taller_person_in_frame_reads_as_closer():
    feedback = VisualFeedback(smoothing_s=0.0)
    feedback._distance.time_constant_s = 0.0
    far = feedback.update((300, 220, 340, 260), FRAME, 0.05).distance_cm
    feedback.clear()
    near = feedback.update((300, 10, 340, 470), FRAME, 0.05).distance_cm
    assert near < far


def test_a_dropped_frame_does_not_immediately_lose_the_target():
    feedback = VisualFeedback(smoothing_s=0.0, target_timeout_s=10.0)
    feedback.update((300, 100, 340, 400), FRAME, 0.05, score=0.9)
    assert feedback.update(None, FRAME, 0.05) is not None


def test_smoothing_damps_a_jittery_detection():
    smooth = VisualFeedback(smoothing_s=0.5)
    smooth.update((300, 100, 340, 400), FRAME, 0.05, score=0.9)
    jumped = smooth.update((600, 100, 640, 400), FRAME, 0.05, score=0.9)
    assert jumped.bearing < 0.5  # Not the raw +0.95.


def test_confidence_is_reported_to_the_bus():
    feedback = VisualFeedback(smoothing_s=0.0)
    assert feedback.poll().confidence == 0.0
    feedback.update((300, 100, 340, 400), FRAME, 0.05, score=0.9)
    assert feedback.poll().confidence > 0.5


# -- wheel encoders (future hardware) ------------------------------------
def test_the_encoder_segment_is_off_by_default():
    encoder = WheelEncoderFeedback()
    assert encoder.enabled is False
    assert encoder.poll().confidence == 0.0


def test_encoder_geometry_converts_ticks_to_metres():
    geometry = EncoderGeometry(ticks_per_revolution=20, wheel_diameter_m=0.065)
    assert geometry.metres_per_tick == pytest.approx(math.pi * 0.065 / 20)


def test_encoder_geometry_rejects_impossible_values():
    with pytest.raises(ValueError):
        EncoderGeometry(ticks_per_revolution=0)
    with pytest.raises(ValueError):
        EncoderGeometry(wheel_diameter_m=-1.0)


def test_equal_ticks_mean_straight_ahead():
    encoder = WheelEncoderFeedback()
    encoder.enabled = True
    encoder.inject_ticks(20, 20)
    estimate = encoder.poll()
    assert estimate.distance_m > 0
    assert estimate.heading_rad == pytest.approx(0.0)


def test_unequal_ticks_mean_a_turn():
    encoder = WheelEncoderFeedback()
    encoder.enabled = True
    encoder.inject_ticks(0, 20)
    assert encoder.poll().heading_rad > 0


def test_encoder_reset_clears_odometry():
    encoder = WheelEncoderFeedback()
    encoder.enabled = True
    encoder.inject_ticks(20, 10)
    encoder.poll()
    encoder.reset()
    assert encoder.poll().distance_m in (0.0, None)


# -- IMU (future hardware) -----------------------------------------------
def test_the_imu_segment_is_off_by_default():
    assert ImuFeedback().enabled is False


def test_a_simulated_imu_never_outranks_the_camera():
    """A placeholder driver must not be selected by the fusion bus."""
    imu = ImuFeedback(enabled=True)
    assert imu.poll().confidence == 0.0


def test_a_supplied_driver_is_trusted():
    imu = ImuFeedback(reader=SimulatedImuReader(), enabled=True)
    assert imu.poll().confidence > 0.5


def test_gyro_bias_is_calibrated_out():
    class BiasedReader:
        def read_gyro_rps(self):
            return (0.0, 0.0, 0.02)

        def read_accel_mps2(self):
            return (0.0, 0.0, 9.81)

    imu = ImuFeedback(reader=BiasedReader(), enabled=True)
    assert imu.calibrate(samples=10, delay_s=0.0) == pytest.approx(0.02)
    for _ in range(100):
        imu.poll()
    assert imu.heading_deg == pytest.approx(0.0, abs=1.0)


# -- the bus -------------------------------------------------------------
def test_the_bus_picks_the_most_confident_fresh_source():
    bus = FeedbackBus()
    visual = VisualFeedback(smoothing_s=0.0)
    encoder = WheelEncoderFeedback()
    bus.add(visual)
    bus.add(encoder)
    visual.update((300, 100, 340, 400), FRAME, 0.05, score=0.9)
    bus.poll()
    best = bus.best()
    assert best is not None and best.confidence > 0.5


def test_the_bus_reports_nothing_when_no_source_is_usable():
    bus = FeedbackBus()
    bus.add(WheelEncoderFeedback())
    bus.poll()
    assert bus.best() is None


def test_a_broken_source_cannot_stop_the_control_loop():
    class BrokenSource:
        name = "broken"
        enabled = True

        def poll(self):
            raise RuntimeError("sensor on fire")

        def reset(self):
            raise RuntimeError("still on fire")

        def close(self):
            raise RuntimeError("nope")

    bus = FeedbackBus()
    bus.add(BrokenSource())
    bus.add(WheelEncoderFeedback())
    bus.poll()      # Must not raise.
    bus.reset()
    bus.close()
    assert bus.best() is None


def test_stale_estimates_are_not_selected():
    bus = FeedbackBus(max_age_s=0.01)
    bus._estimates = {"old": MotionEstimate(confidence=1.0, timestamp=0.0)}
    assert bus.best() is None


def test_the_bus_is_serialisable_for_telemetry():
    import json

    bus = FeedbackBus()
    bus.add(VisualFeedback(smoothing_s=0.0))
    bus.poll()
    json.dumps(bus.as_dict())
