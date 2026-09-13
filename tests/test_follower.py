"""Person-following tests: does it approach, hold, corner and stop safely?"""

from __future__ import annotations

import pytest

from anna_robot.control.follower import FollowState, FollowTuning, PersonFollower
from anna_robot.control.visual import VisualFeedback

FRAME = (640, 480)
DT = 0.05


def run(follower, box, sonar_cm, seconds=3.0, feedback=None, search=True):
    """Drive the follower with a fixed target for a while."""
    feedback = feedback or VisualFeedback(smoothing_s=0.05)
    command = None
    for _ in range(int(seconds / DT)):
        target = feedback.update(box, FRAME, DT, score=0.9, sonar_distance_cm=sonar_cm)
        command = follower.update(target, DT, obstacle_cm=sonar_cm, search_when_lost=search)
    return command


def centred_box():
    return (290, 80, 390, 430)


def test_drives_forward_when_the_person_is_far():
    command = run(PersonFollower(), centred_box(), 250.0)
    assert command.state is FollowState.APPROACHING
    assert command.linear > 0.3


def test_holds_still_inside_the_comfort_band():
    command = run(PersonFollower(), centred_box(), 90.0)
    assert command.state is FollowState.HOLDING
    assert command.linear == 0.0


def test_does_not_reverse_when_too_close():
    """The chassis cannot reverse, so 'too close' must mean 'stop'."""
    command = run(PersonFollower(), centred_box(), 40.0)
    assert command.linear == 0.0


def test_arrival_hysteresis_stops_the_robot_creeping():
    follower = PersonFollower()
    feedback = VisualFeedback(smoothing_s=0.05)
    run(follower, centred_box(), 90.0, feedback=feedback)
    # Just outside the band is not enough to set off again...
    command = run(follower, centred_box(), 105.0, feedback=feedback)
    assert command.state is FollowState.HOLDING
    # ...but a clear step away is.
    command = run(follower, centred_box(), 170.0, feedback=feedback)
    assert command.state is FollowState.APPROACHING


def test_turns_right_for_a_target_on_the_right():
    command = run(PersonFollower(), (520, 80, 620, 430), 250.0)
    assert command.angular < -0.1


def test_turns_left_for_a_target_on_the_left():
    command = run(PersonFollower(), (20, 80, 120, 430), 250.0)
    assert command.angular > 0.1


def test_slows_down_while_cornering():
    straight = run(PersonFollower(), centred_box(), 250.0)
    turning = run(PersonFollower(), (600, 80, 640, 430), 250.0)
    assert turning.linear < straight.linear


def test_obstacle_inside_the_stop_distance_cuts_forward_motion():
    command = run(PersonFollower(), (290, 80, 390, 200), 15.0)
    assert command.state is FollowState.BLOCKED
    assert command.linear == 0.0


def test_losing_the_target_coasts_before_searching():
    follower = PersonFollower()
    run(follower, centred_box(), 250.0)
    first = follower.update(None, DT)
    assert first.state is FollowState.LOST
    for _ in range(40):
        command = follower.update(None, DT)
    assert command.state is FollowState.SEARCHING
    assert command.linear == 0.0  # Never drives blind.


def test_search_sweeps_toward_where_the_person_was_last_seen():
    follower = PersonFollower()
    run(follower, (600, 80, 640, 430), 250.0)  # Last seen on the right.
    for _ in range(60):
        command = follower.update(None, DT)
    assert command.state is FollowState.SEARCHING
    assert command.angular < 0.0  # Sweeping right.


def test_search_eventually_gives_up():
    follower = PersonFollower(FollowTuning(search_timeout_s=1.0))
    run(follower, centred_box(), 250.0)
    for _ in range(200):
        command = follower.update(None, DT)
    assert follower.gave_up is True
    assert command.state is FollowState.IDLE
    assert (command.linear, command.angular) == (0.0, 0.0)


def test_commands_are_acceleration_limited():
    """A standing start must ramp, not jump to full speed."""
    follower = PersonFollower()
    feedback = VisualFeedback(smoothing_s=0.0)
    target = feedback.update(centred_box(), FRAME, DT, score=0.9, sonar_distance_cm=300.0)
    previous = 0.0
    for _ in range(20):
        command = follower.update(target, DT, obstacle_cm=300.0)
        assert command.linear - previous <= follower.tuning.linear_slew_per_s * DT + 1e-6
        previous = command.linear


def test_reset_clears_state():
    follower = PersonFollower()
    run(follower, centred_box(), 250.0)
    follower.reset()
    assert follower.command.linear == 0.0
    assert follower.state is FollowState.IDLE


def test_tuning_rejects_a_hold_distance_inside_the_stop_distance():
    with pytest.raises(ValueError, match="safety_stop_cm"):
        FollowTuning(target_distance_cm=20.0, safety_stop_cm=25.0)
