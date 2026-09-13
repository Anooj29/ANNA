"""Target-tracking tests: does the lock survive gaps and reject jumps?"""

from __future__ import annotations

import time

from anna_robot.perception.object_detector import Detection
from anna_robot.perception.tracker import TargetTracker

FRAME = (640, 480)
DT = 0.05


def person(xmin, score=0.9, width=100):
    return Detection("person", score, (xmin, 100, xmin + width, 400))


def test_confirmation_requires_several_sightings():
    tracker = TargetTracker(confirm_hits=3)
    tracker.update([person(300)], FRAME, DT)
    assert tracker.has_target and not tracker.is_confirmed
    tracker.update([person(305)], FRAME, DT)
    tracker.update([person(310)], FRAME, DT)
    assert tracker.is_confirmed


def test_a_single_missed_frame_does_not_lose_the_target():
    """The old frame counter reset to zero here, making the robot flap."""
    tracker = TargetTracker(confirm_hits=2)
    for offset in (300, 305, 310):
        tracker.update([person(offset)], FRAME, DT)
    assert tracker.is_confirmed
    tracker.update([], FRAME, DT)  # One dropped detection.
    assert tracker.has_target and tracker.is_confirmed


def test_target_is_dropped_after_too_many_misses():
    tracker = TargetTracker(confirm_hits=1, max_misses=3)
    tracker.update([person(300)], FRAME, DT)
    for _ in range(4):
        tracker.update([], FRAME, DT)
    assert tracker.has_target is False


def test_target_is_dropped_once_the_coast_window_expires():
    tracker = TargetTracker(confirm_hits=1, max_misses=1000, max_coast_s=0.05)
    tracker.update([person(300)], FRAME, DT)
    time.sleep(0.08)
    tracker.update([], FRAME, DT)
    assert tracker.has_target is False


def test_the_tracker_stays_on_the_same_person_when_another_appears():
    tracker = TargetTracker(confirm_hits=1)
    tracker.update([person(300)], FRAME, DT)
    original = tracker.track.box
    tracker.update([person(310), person(20)], FRAME, DT)
    assert abs(tracker.track.box[0] - original[0]) < 50


def test_a_detection_across_the_frame_is_not_accepted_as_the_same_person():
    tracker = TargetTracker(confirm_hits=1, max_center_jump_fraction=0.2)
    tracker.update([person(20)], FRAME, DT)
    tracker.update([person(600)], FRAME, DT)
    assert tracker.track.misses == 1  # Treated as a miss, not a teleport.


def test_velocity_is_estimated_from_movement():
    tracker = TargetTracker(confirm_hits=1)
    tracker.update([person(200)], FRAME, DT)
    tracker.update([person(260)], FRAME, DT)
    assert tracker.track.velocity[0] > 0


def test_non_person_detections_are_ignored():
    tracker = TargetTracker(label="person")
    tracker.update([Detection("chair", 0.9, (0, 0, 100, 100))], FRAME, DT)
    assert tracker.has_target is False


def test_clear_drops_the_lock():
    tracker = TargetTracker(confirm_hits=1)
    tracker.update([person(300)], FRAME, DT)
    tracker.clear()
    assert tracker.has_target is False


def test_prediction_stays_inside_the_frame():
    tracker = TargetTracker(confirm_hits=1)
    tracker.update([person(600)], FRAME, DT)
    tracker.update([person(620)], FRAME, DT)
    xmin, ymin, xmax, ymax = tracker.track.predict(5.0, FRAME)
    assert 0 <= xmin <= 640 and 0 <= xmax <= 640
    assert 0 <= ymin <= 480 and 0 <= ymax <= 480
