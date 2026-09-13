"""End-to-end state-machine tests against a fully simulated robot.

The robot is assembled with fake hardware (simulated GPIO, a synthetic
camera, a fake detector, no network) so the whole behaviour chain -
detection, following, dialogue, the health check - can be exercised in
milliseconds without a Raspberry Pi.
"""

from __future__ import annotations


import numpy as np
import pytest

from anna_robot.config import Config
from anna_robot.state import HealthStage, RobotState

from .fake_tflite import FakeSsdInterpreter

FRAME_SIZE = (480, 640)
PERSON_NEAR = (0, 0.95, [0.1, 0.35, 0.95, 0.65])   # Centred, large (close).
PERSON_FAR = (0, 0.95, [0.40, 0.46, 0.60, 0.54])    # Centred, small (far).


class FakeCamera:
    """A synthetic camera that always has a frame ready."""

    def __init__(self, *args, **kwargs):
        self.index = 0
        self.fps = 30.0
        self.age_s = 0.0
        self.frame_id = 0
        self.released = False

    def read(self, timeout=None):
        self.frame_id += 1
        return np.zeros((*FRAME_SIZE, 3), np.uint8)

    def release(self):
        self.released = True


class FakeEmotionDetector:
    available = True

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def load_or_null(cls, model_path, **kwargs):
        return cls()

    def detect(self, face_bgr):
        return "Happy"


class FakeFaceIdentifier:
    """Recognises one patient, or nobody, depending on how it is built."""

    def __init__(self, *args, **kwargs):
        self.name = "Ada"
        self.available = True
        self.has_known_faces = True
        self.locations = [(100, 400, 300, 200)]

    def locate(self, frame):
        return list(self.locations)

    def encode(self, frame, locations, limit=1):
        return [np.zeros(128)] if locations else []

    def match(self, encoding):
        return (self.name, 0.3) if self.name else (None, 0.9)

    @staticmethod
    def crop(frame, location, margin=0.0):
        return np.zeros((64, 64, 3), np.uint8)


@pytest.fixture
def robot(monkeypatch):
    """A fully assembled robot with every piece of hardware faked out."""
    import anna_robot.robot as robot_module

    interpreter = type("Configured", (FakeSsdInterpreter,), {"detections": ()})
    monkeypatch.setattr("anna_robot.perception.object_detector.load_interpreter_factory",
                        lambda: interpreter)
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr(robot_module, "ThreadedCamera", FakeCamera)
    monkeypatch.setattr(robot_module, "EmotionDetector", FakeEmotionDetector)
    monkeypatch.setattr(robot_module, "FaceIdentifier", FakeFaceIdentifier)

    config = Config(
        simulate_hardware=True,
        tcp_port=0,
        tcp_wait_for_client=False,
        show_debug_window=False,
        vision_stream_enabled=False,
        head_pan_pin=12,
        head_tilt_pin=13,
        control_loop_fps=0.0,
        face_check_interval_s=0.0,
        person_confirm_frames=2,
        done_pause_s=0.0,
    )
    robot = robot_module.HealthcareRobot(config)
    # The no-TTS fallback paces itself in real time to keep the conversation
    # realistic; tests do not need to sit through it.
    robot.voice._render = lambda message: None
    yield robot
    robot.shutdown()


def set_detections(robot, detections):
    type(robot.object_detector._interpreter).detections = tuple(detections)


def tick(robot, detections=(), utterances=(), dt=0.05, distance=None, count=1):
    """Run ``count`` control-loop iterations without the camera or display."""
    set_detections(robot, detections)
    frame = np.zeros((*FRAME_SIZE, 3), np.uint8)
    for _ in range(count):
        robot.frame_number += 1
        sonar = 400.0 if distance is None else distance
        robot._perceive(frame, dt, sonar)
        robot.head.update(robot.visual_feedback.target, dt)
        parsed = robot.router.parse_all(utterances)
        if not robot._handle_global_intents(parsed):
            robot._step(frame, sonar, parsed, dt)
        utterances = ()  # Commands are delivered once, not every tick.
    return robot


def wait_for_speech(robot):
    robot.voice.wait_until_idle(timeout=10.0)


def run_until(robot, predicate, detections=(), utterances=(), max_ticks=60, distance=None):
    """Tick until ``predicate(robot)`` holds, or fail with what happened.

    Asserting on an exact tick count would make these tests brittle - what
    matters is that the robot *gets there*.
    """
    pending = list(utterances)
    for _ in range(max_ticks):
        wait_for_speech(robot)
        tick(robot, detections, pending, distance=distance)
        pending = []
        if predicate(robot):
            return robot
    raise AssertionError(
        f"Condition never met. state={robot.state} stage={robot.health_stage} "
        f"answers={robot.session.answers}"
    )


# -- start-up -----------------------------------------------------------
def test_robot_builds_and_reaches_search(robot):
    assert robot.state is RobotState.STARTUP
    tick(robot)
    assert robot.state is RobotState.SEARCH


def test_invalid_configuration_is_refused_before_anything_moves():
    from anna_robot.robot import HealthcareRobot

    with pytest.raises(ValueError, match="Invalid robot configuration"):
        HealthcareRobot(Config(safety_stop_cm=500.0))


# -- search and approach -------------------------------------------------
def test_robot_stands_still_with_nobody_in_sight(robot):
    tick(robot, count=5)
    assert robot.motors.duties == (0.0, 0.0)


def test_robot_approaches_a_distant_person(robot):
    tick(robot)  # STARTUP -> SEARCH
    tick(robot, [PERSON_FAR], distance=300.0, count=20)
    assert robot.state is RobotState.SEARCH
    assert robot.motors.is_moving is True
    assert robot._drive.linear > 0.0


def test_robot_greets_a_person_who_is_close_enough(robot):
    tick(robot)
    run_until(robot, lambda r: r.state is not RobotState.SEARCH,
              [PERSON_NEAR], distance=50.0)
    assert robot.state in (RobotState.INTERACT, RobotState.WAIT_CONFIRM)
    assert robot.motors.duties == (0.0, 0.0)


def test_an_obstacle_stops_forward_motion(robot):
    tick(robot)
    # Far target (so no greeting) but something right in front of the robot.
    robot.config.distance_trigger_cm = 10.0
    tick(robot, [PERSON_FAR], distance=15.0, count=20)
    assert robot._drive.linear == 0.0


# -- recognition ---------------------------------------------------------
def test_a_recognised_patient_is_greeted_and_waits_for_confirmation(robot):
    tick(robot)
    run_until(robot, lambda r: r.state is RobotState.WAIT_CONFIRM,
              [PERSON_NEAR], distance=50.0)
    assert robot.session.name == "Ada"
    assert robot.session.emotion == "Happy"
    assert robot.greeted is True


def test_an_unrecognised_person_is_turned_away_after_three_attempts(robot):
    robot.face_identifier.name = None
    tick(robot)
    run_until(robot, lambda r: r.state is RobotState.INTERACT, [PERSON_NEAR], distance=50.0)
    attempts_seen = []
    run_until(
        robot,
        lambda r: attempts_seen.append(r.unknown_attempts) or r.state is RobotState.SEARCH,
        [PERSON_NEAR], distance=50.0,
    )
    assert max(attempts_seen) >= 2  # More than one chance before giving up.
    assert robot.session.name == "--"
    assert robot.unknown_attempts == 0  # Counter reset for the next person.


def test_the_unknown_attempt_limit_is_honoured_exactly(robot):
    robot.state = RobotState.INTERACT
    for attempt in range(1, robot.config.max_unknown_attempts):
        robot._on_unknown(best_distance=0.9)
        assert robot.state is RobotState.INTERACT, f"gave up on attempt {attempt}"
    robot._on_unknown(best_distance=0.9)
    assert robot.state is RobotState.SEARCH


def test_no_face_for_too_long_returns_to_search(robot):
    robot.face_identifier.locations = []
    robot.config.max_no_face_frames = 3
    tick(robot)
    run_until(robot, lambda r: r.state is RobotState.INTERACT, [PERSON_NEAR], distance=50.0)
    run_until(robot, lambda r: r.state is RobotState.SEARCH, [PERSON_NEAR], distance=50.0)


# -- the health check ----------------------------------------------------
def reach_wait_confirm(robot):
    tick(robot)
    run_until(robot, lambda r: r.state is RobotState.WAIT_CONFIRM, [PERSON_NEAR], distance=50.0)


def test_hey_anna_starts_the_health_check(robot):
    reach_wait_confirm(robot)
    tick(robot, [PERSON_NEAR], ["hey anna, start my health check"], distance=50.0)
    assert robot.state is RobotState.HEALTH_CHECK


@pytest.mark.parametrize("phrase", ["yes buddy", "yes anna", "hey anna start my health check", "yes"])
def test_every_way_of_saying_yes_starts_the_health_check(robot, phrase):
    """Backward compatibility: 'yes buddy' alone must still start it."""
    reach_wait_confirm(robot)
    wait_for_speech(robot)
    tick(robot, [PERSON_NEAR], [phrase], distance=50.0)
    assert robot.state is RobotState.HEALTH_CHECK


def test_the_health_check_walks_through_its_stages(robot):
    reach_wait_confirm(robot)
    run_until(robot, lambda r: r.state is RobotState.HEALTH_CHECK,
              [PERSON_NEAR], ["hey anna start health check"], distance=50.0)

    run_until(robot, lambda r: r.health_stage is HealthStage.WAIT_TEMP,
              [PERSON_NEAR], distance=50.0)
    run_until(robot, lambda r: r.session.temperature != "--",
              [PERSON_NEAR], ["check temperature"], distance=50.0)

    run_until(robot, lambda r: r.health_stage is HealthStage.WAIT_PULSE,
              [PERSON_NEAR], distance=50.0)
    run_until(robot, lambda r: r.session.pulse != "--",
              [PERSON_NEAR], ["check pulse"], distance=50.0)
    assert robot.session.pulse.endswith("BPM")

    run_until(robot, lambda r: r.health_stage is HealthStage.WAIT_ECG,
              [PERSON_NEAR], distance=50.0)


def test_a_stray_command_is_not_recorded_as_a_questionnaire_answer(robot):
    """'check my pulse' is a command, not an answer to 'how did you sleep?'."""
    robot.state = RobotState.HEALTH_CHECK
    robot.health_stage = HealthStage.WAIT_ANSWER
    robot.question_index = 0
    robot.router.wake()
    wait_for_speech(robot)
    tick(robot, [PERSON_NEAR], ["check my pulse"], distance=50.0)
    assert "sleep" not in robot.session.answers

    robot.health_stage = HealthStage.WAIT_ANSWER
    wait_for_speech(robot)
    tick(robot, [PERSON_NEAR], ["seven hours"], distance=50.0)
    assert robot.session.answers.get("sleep") == "seven hours"


def test_the_summary_waits_for_gemini_without_blocking(robot):
    robot.session.name = "Ada"
    robot.state = RobotState.HEALTH_CHECK
    robot._request_summary()
    assert robot.health_stage is HealthStage.SUMMARISE
    run_until(robot, lambda r: r.state is RobotState.DONE, [PERSON_NEAR], distance=50.0)
    assert robot.session.health_report != "--"
    assert robot.session.clinical_report.endswith("not diagnostic.")


def test_done_resumes_searching_without_sleeping(robot):
    """The old code sat in time.sleep(10) here, blind and deaf."""
    robot.state = RobotState.DONE
    robot._pause.arm(0.0)
    tick(robot, count=2)
    assert robot.state is RobotState.SEARCH
    assert robot.session.name == "--"


# -- following -----------------------------------------------------------
def test_follow_me_starts_following(robot):
    tick(robot)
    tick(robot, [PERSON_FAR], ["hey anna follow me"], distance=200.0)
    assert robot.state is RobotState.FOLLOW


def test_following_drives_toward_a_distant_person(robot):
    tick(robot)
    tick(robot, [PERSON_FAR], ["hey anna follow me"], distance=200.0)
    tick(robot, [PERSON_FAR], distance=200.0, count=25)
    assert robot._drive.linear > 0.0


def test_following_holds_station_at_the_right_distance(robot):
    tick(robot)
    tick(robot, [PERSON_NEAR], ["hey anna follow me"], distance=90.0)
    tick(robot, [PERSON_NEAR], distance=90.0, count=25)
    assert robot._drive.linear == 0.0
    assert robot.motors.duties == (0.0, 0.0)


def test_stop_following_returns_to_search(robot):
    tick(robot)
    tick(robot, [PERSON_FAR], ["hey anna follow me"], distance=200.0)
    tick(robot, [PERSON_FAR], ["stop following"], distance=200.0)
    assert robot.state is RobotState.SEARCH
    assert robot.motors.duties == (0.0, 0.0)


def test_emergency_stop_works_in_any_state(robot):
    tick(robot)
    tick(robot, [PERSON_FAR], ["hey anna follow me"], distance=200.0)
    tick(robot, [PERSON_FAR], distance=200.0, count=20)
    assert robot.motors.is_moving
    tick(robot, [PERSON_FAR], ["stop"], distance=200.0)
    assert robot.motors.duties == (0.0, 0.0)
    assert robot.state is not RobotState.FOLLOW


def test_stop_stays_stopped_instead_of_driving_off_again(robot):
    """Without the hold, the very next tick would see the person and go."""
    tick(robot)
    tick(robot, [PERSON_FAR], distance=200.0, count=20)
    assert robot.motors.is_moving
    tick(robot, [PERSON_FAR], ["stop"], distance=200.0)
    tick(robot, [PERSON_FAR], distance=200.0, count=30)
    assert robot.motors.duties == (0.0, 0.0)


def test_an_explicit_move_command_overrides_the_stop_hold(robot):
    tick(robot)
    tick(robot, [PERSON_FAR], ["stop"], distance=200.0)
    tick(robot, [PERSON_FAR], ["hey anna follow me"], distance=200.0)
    assert robot.state is RobotState.FOLLOW
    tick(robot, [PERSON_FAR], distance=200.0, count=25)
    assert robot.motors.is_moving


def test_the_stop_hold_expires(robot):
    robot.config.emergency_stop_hold_s = 0.0
    tick(robot)
    tick(robot, [PERSON_FAR], ["stop"], distance=200.0)
    tick(robot, [PERSON_FAR], distance=200.0, count=25)
    assert robot.motors.is_moving


# -- conversation --------------------------------------------------------
def test_anna_answers_to_her_name(robot):
    tick(robot)
    tick(robot, [], ["hey anna"])
    assert robot.router.is_attentive is True


def test_anna_describes_what_she_can_see(robot):
    tick(robot)
    chair = (56, 0.8, [0.5, 0.6, 0.9, 0.9])
    tick(robot, [PERSON_NEAR, chair], count=2)
    assert set(robot.visible_objects()) == {"person", "chair"}
    tick(robot, [PERSON_NEAR, chair], ["hey anna what do you see"])
    wait_for_speech(robot)
    assert "chair" in robot.voice.last_spoken


def test_anna_says_who_the_patient_is(robot):
    robot.session.name = "Ada"
    tick(robot, [], ["hey anna who am i"])
    wait_for_speech(robot)
    assert "Ada" in robot.voice.last_spoken


# -- head tracking -------------------------------------------------------
def test_the_head_follows_the_person_while_the_body_works(robot):
    tick(robot)
    right_of_frame = (0, 0.95, [0.3, 0.75, 0.9, 0.95])
    tick(robot, [right_of_frame], distance=200.0, count=40)
    assert robot.head.angles[0] < -2.0  # Panned right, toward the person.


def test_head_angles_stay_within_their_limits_throughout(robot):
    tick(robot)
    far_right = (0, 0.95, [0.8, 0.95, 0.99, 1.0])
    for _ in range(200):
        tick(robot, [far_right], distance=200.0)
        pan, tilt = robot.head.angles
        assert robot.config.head_pan_min_deg <= pan <= robot.config.head_pan_max_deg
        assert robot.config.head_tilt_min_deg <= tilt <= robot.config.head_tilt_max_deg


# -- telemetry -----------------------------------------------------------
def test_telemetry_keeps_every_original_field(robot):
    """Existing companion apps must not break on the new packet."""
    payload = robot.session.to_telemetry(42.0, "SEARCH", robot._status_extra())
    for key in ("distance", "temp", "pulse", "ecg", "name", "emotion", "state",
                "sleep", "water", "pain", "appetite", "exercise", "stress",
                "health_report", "clinical_report"):
        assert key in payload


def test_telemetry_adds_the_new_diagnostics(robot):
    tick(robot, [PERSON_NEAR], count=3)
    payload = robot.session.to_telemetry(42.0, "SEARCH", robot._status_extra())
    for key in ("fps", "detections", "target", "drive", "head", "feedback", "pid"):
        assert key in payload
    assert payload["head"]["pan_min_deg"] == robot.config.head_pan_min_deg


def test_the_whole_packet_is_json_serialisable(robot):
    import json

    tick(robot, [PERSON_NEAR], count=3)
    json.dumps(robot.session.to_telemetry(42.0, "SEARCH", robot._status_extra()))


# -- shutdown ------------------------------------------------------------
def test_shutdown_stops_the_motors_and_releases_everything(robot):
    tick(robot, [PERSON_FAR], distance=300.0, count=20)
    robot.shutdown()
    assert robot.motors.duties == (0.0, 0.0)
    assert robot.camera.released is True


def test_shutdown_is_safe_to_call_twice(robot):
    robot.shutdown()
    robot.shutdown()
