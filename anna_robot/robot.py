"""Top-level state machine tying together perception, motor control,
sensors, voice, the head and the telemetry link.

The loop's contract is simple and worth stating, because everything else
follows from it: **nothing in the control loop may block.** Frames arrive
from a capture thread, distance from a sampling thread, speech is queued to
a worker thread, and Gemini calls run in the background and are collected
when ready. The loop itself only does arithmetic and decisions, so obstacle
sensing, head tracking and telemetry keep running at full rate even while
ANNA is talking or thinking.

Behaviour states:

* ``SEARCH``       - look for a person and approach them under PID control.
* ``INTERACT``     - identify the person and greet them.
* ``WAIT_CONFIRM`` - wait for "hey ANNA, start my health check" (or the
  original "yes buddy").
* ``HEALTH_CHECK`` - readings, then the questionnaire, then the summary.
* ``FOLLOW``       - walk with the person until told to stop.
* ``DONE``         - a pause, then back to SEARCH for the next patient.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

import cv2
import numpy as np

from .config import Config
from .control import (
    DriveCommand,
    EncoderGeometry,
    FeedbackBus,
    FollowState,
    FollowTuning,
    ImuFeedback,
    PersonFollower,
    PidGains,
    VisualFeedback,
    WheelEncoderFeedback,
)
from .gemini_assistant import GeminiAssistant
from .hardware import ThreadedCamera, backend_name, get_gpio, use_simulation
from .head_tracker import HeadTracker, HeadTuning
from .interaction import CommandRouter, DialogueManager, Intent, MicrophoneListener, Utterance
from .motors import MotorController, MotorTuning
from .overlay import draw_detections, draw_drive, draw_faces, draw_head, draw_status, draw_target
from .patient_session import PatientSession
from .perception import EmotionDetector, FaceIdentifier, ObjectDetector, TargetTracker
from .perception.labels import PERSON_LABEL
from .sensors import EcgSensor, SimulatedPulseSensor, TemperatureSensor, UltrasonicSensor
from .state import (
    HEALTH_QUESTIONS,
    HealthStage,
    RobotState,
    looks_like_answer,
    question_for,
)
from .telemetry import TelemetryLink
from .utils import Deadline, LoopTimer, RateLimiter
from .vision_stream import VisionStream
from .voice import VoiceAssistant

logger = logging.getLogger(__name__)


class HealthcareRobot:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = PatientSession()

        problems = config.validate()
        if problems:
            raise ValueError(
                "Invalid robot configuration:\n  - " + "\n  - ".join(problems)
            )
        logger.debug(config.describe())

        self.state: RobotState = RobotState.STARTUP
        self.health_stage: Optional[HealthStage] = None
        self.question_index = 0
        self.greeted = False
        self.unknown_attempts = 0
        self.no_face_count = 0
        self.frame_number = 0

        self._pause = Deadline()
        # Armed by "stop": autonomous motion is suspended until it expires,
        # otherwise the next control tick would simply drive off again.
        self._motion_hold = Deadline()
        self._face_check = RateLimiter(config.face_check_interval_s)
        self._loop = LoopTimer(target_fps=config.control_loop_fps)
        self._detections: List = []
        self._face_locations: List = []
        self._face_caption: Optional[str] = None
        self._drive = DriveCommand()
        self._awaiting_greeting = False
        self._return_state_after_follow = RobotState.SEARCH

        # Anything already built is torn down if a later step fails, so a
        # partial start-up cannot leave motors energised or a port bound.
        self._built: List = []
        try:
            self._build()
        except Exception:
            logger.exception("Robot start-up failed; shutting down what was already started.")
            self.shutdown()
            raise

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build(self) -> None:
        config = self.config

        if config.simulate_hardware:
            use_simulation()
            logger.warning("Running with SIMULATED hardware: no motors, servos or GPIO sensors will move.")
        gpio = get_gpio()
        gpio.setwarnings(False)
        gpio.setmode(gpio.BCM)
        logger.info("GPIO backend in use: %s", backend_name())

        self.voice = self._track(VoiceAssistant(
            rate=config.tts_rate,
            reinit_each_call=config.reinit_tts_each_call,
            volume=config.tts_volume,
            voice_id=config.tts_voice_id,
        ))
        self.dialogue = DialogueManager(voice=self.voice)
        self.router = CommandRouter(
            attention_window_s=config.wake_attention_window_s,
            require_wake_word=config.require_wake_word,
        )
        self.listener = self._track(MicrophoneListener(
            enabled=config.mic_enabled,
            device_index=config.mic_device_index,
            language=config.mic_language,
        ))

        self.motors = self._track(MotorController(
            config.left_dir_pin, config.left_pwm_pin, config.right_dir_pin, config.right_pwm_pin,
            tuning=MotorTuning(
                min_duty=config.motor_min_duty,
                max_duty=config.motor_max_duty,
                ramp_duty_per_s=config.motor_ramp_duty_per_s,
            ),
            allow_reverse=config.motor_allow_reverse,
        ))
        self.ultrasonic = self._track(UltrasonicSensor(config.trig_pin, config.echo_pin))
        self.temperature_sensor = TemperatureSensor()
        self.pulse_sensor = SimulatedPulseSensor()
        self.ecg_sensor = EcgSensor(config.ecg_lo_plus_pin, config.ecg_lo_minus_pin)

        self.object_detector = ObjectDetector(
            model_path=config.person_model_path,
            score_threshold=config.person_detection_threshold,
            classes_of_interest=config.detection_classes,
            label_path=config.label_map_path,
            num_threads=config.inference_threads,
        )
        self.tracker = TargetTracker(
            label=PERSON_LABEL, confirm_hits=max(config.person_confirm_frames, 1)
        )
        self.face_identifier = FaceIdentifier(
            config.known_faces_dir, config.face_match_threshold,
            detection_scale=config.face_detection_scale,
        )
        self.emotion_detector = EmotionDetector.load_or_null(config.emotion_model_path)
        self.gemini = self._track(GeminiAssistant(
            config.gemini_api_key, config.gemini_model, request_timeout_s=config.gemini_timeout_s
        ))

        self._build_control()
        self.head = self._track(self._build_head())

        self.camera = self._track(ThreadedCamera(
            indices=config.camera_indices,
            width=config.camera_width,
            height=config.camera_height,
            fps=config.camera_fps,
            use_mjpg=config.camera_use_mjpg,
        ))
        self.vision_stream = self._track(VisionStream(
            config.vision_stream_host, config.vision_stream_port, config.vision_stream_token,
            jpeg_quality=config.vision_stream_quality, max_fps=config.vision_stream_fps,
        )) if config.vision_stream_enabled else None

        # The telemetry link is built last: it is the only step that can
        # wait for a human, and by now everything else is known to work.
        self.telemetry = self._track(TelemetryLink(
            config.tcp_port,
            wait_for_client=config.tcp_wait_for_client,
            connect_timeout_s=config.tcp_connect_timeout_s,
        ))

    def _track(self, resource):
        """Register a resource so :meth:`shutdown` closes it in reverse order."""
        self._built.append(resource)
        return resource

    def _build_control(self) -> None:
        """Wire up the feedback sources and the person follower."""
        config = self.config
        self.visual_feedback = VisualFeedback(target_timeout_s=1.0)
        self.encoder_feedback = WheelEncoderFeedback(
            left_pin=config.encoder_left_pin,
            right_pin=config.encoder_right_pin,
            geometry=EncoderGeometry(
                ticks_per_revolution=config.encoder_ticks_per_rev,
                wheel_diameter_m=config.wheel_diameter_m,
                wheel_base_m=config.wheel_base_m,
            ),
            enabled=config.encoder_enabled,
        )
        self.imu_feedback = ImuFeedback(enabled=config.imu_enabled)

        self.feedback = FeedbackBus()
        for source in (self.visual_feedback, self.encoder_feedback, self.imu_feedback):
            self.feedback.add(source)
        self._track(self.feedback)

        bearing_gains = PidGains(
            kp=config.bearing_kp, ki=config.bearing_ki, kd=config.bearing_kd,
            output_limit=1.0, integral_limit=0.25, derivative_filter_s=0.10, deadband=0.05,
        )
        range_gains = PidGains(
            kp=config.range_kp, ki=config.range_ki, kd=config.range_kd,
            output_limit=1.0, integral_limit=0.30, derivative_filter_s=0.15, deadband=0.02,
        )
        # Two followers: one holds greeting distance while approaching a new
        # person, the other walks with them. Separate instances mean their
        # integrators never leak state across a mode change.
        self.approach_follower = PersonFollower(
            FollowTuning(
                target_distance_cm=config.distance_trigger_cm,
                safety_stop_cm=config.safety_stop_cm,
                max_linear=config.follow_max_linear,
                max_angular=config.follow_max_angular,
                search_timeout_s=config.follow_search_timeout_s,
            ),
            bearing_gains, range_gains,
        )
        self.follower = PersonFollower(
            FollowTuning(
                target_distance_cm=config.follow_distance_cm,
                hold_band_cm=config.follow_hold_band_cm,
                safety_stop_cm=config.safety_stop_cm,
                max_linear=config.follow_max_linear,
                max_angular=config.follow_max_angular,
                search_timeout_s=config.follow_search_timeout_s,
            ),
            bearing_gains, range_gains,
        )

    def _build_head(self) -> HeadTracker:
        from .hardware.servo import ServoLimits

        config = self.config
        return HeadTracker(
            pan_pin=config.head_pan_pin,
            tilt_pin=config.head_tilt_pin,
            pan_limits=ServoLimits(
                config.head_pan_min_deg, config.head_pan_max_deg,
                max_speed_deg_s=config.head_pan_speed_deg_s,
            ),
            tilt_limits=ServoLimits(
                config.head_tilt_min_deg, config.head_tilt_max_deg,
                max_speed_deg_s=config.head_tilt_speed_deg_s,
            ),
            tuning=HeadTuning(recenter_after_s=config.head_recenter_after_s),
            invert_pan=config.head_invert_pan,
            invert_tilt=config.head_invert_tilt,
            enabled=config.head_enabled,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.dialogue.say(
            "Healthcare robot is now active. I am searching for someone I recognise. "
            "Say, hey ANNA, at any time and I will listen."
        )
        stale_frames = 0
        try:
            while True:
                frame = self.camera.read(timeout=1.0)
                if frame is None:
                    stale_frames += 1
                    if stale_frames % 10 == 1:  # Log periodically, not per frame.
                        logger.warning("No camera frame available (%d in a row).", stale_frames)
                    if stale_frames > 50:
                        raise RuntimeError("Camera stopped returning frames.")
                    self.motors.stop()
                    # Pace the retry so a dead camera cannot spin the CPU.
                    self._loop.sleep_to_rate()
                    continue
                stale_frames = 0

                dt = self._loop.tick()
                self.frame_number += 1
                distance = self.ultrasonic.measure_cm()

                utterances = self._collect_speech()
                self._perceive(frame, dt, distance)
                self.head.update(self.visual_feedback.target, dt)

                if not self._handle_global_intents(utterances):
                    self._step(frame, distance, utterances, dt)

                self._annotate(frame, distance)
                self._publish(frame, distance)

                if self.config.show_debug_window:
                    cv2.imshow("ANNA - Healthcare Robot", frame)
                    if cv2.waitKey(1) == 27:  # Esc quits
                        break

                self._loop.sleep_to_rate()
        except KeyboardInterrupt:
            logger.info("Program stopped by user.")
        finally:
            self.shutdown()

    # -- perception -------------------------------------------------------
    def _perceive(self, frame: np.ndarray, dt: float, distance: float) -> None:
        """Detect, track and turn the result into control-ready feedback.

        Detection runs every ``detect_every_n_frames``; the tracker carries
        the target across the gaps, so the controllers still see a target
        every single frame.
        """
        if self.frame_number % max(self.config.detect_every_n_frames, 1) == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._detections = self.object_detector.detect(rgb)

        frame_size = (frame.shape[1], frame.shape[0])
        track = self.tracker.update(self._detections, frame_size, dt)
        if track is not None and self.tracker.is_confirmed:
            self.visual_feedback.update(
                box=track.box, frame_size=frame_size, dt=dt,
                score=track.detection.score, sonar_distance_cm=distance,
            )
        else:
            self.visual_feedback.update(box=None, frame_size=frame_size, dt=dt)
        self.feedback.poll()

    def visible_objects(self) -> List[str]:
        """Labels currently visible, for "what do you see?"."""
        return [detection.label for detection in self._detections]

    # -- speech input -----------------------------------------------------
    def _collect_speech(self) -> List[Utterance]:
        """Merge the companion link and the microphone into one command list."""
        raw: List[str] = list(self.telemetry.receive_commands())
        raw.extend(self.listener.drain())
        if not raw:
            return []
        # Ignore anything heard while ANNA is speaking: without this the
        # microphone transcribes her own voice back into a command.
        if self.voice.is_speaking and self.config.mic_enabled:
            logger.debug("Ignoring %d utterance(s) heard while speaking.", len(raw))
            return []
        return self.router.parse_all(raw)

    @staticmethod
    def first_intent(utterances: Sequence[Utterance], *wanted: Intent) -> Optional[Utterance]:
        """The first actionable utterance matching any of ``wanted``."""
        for utterance in utterances:
            if utterance.addressed_to_robot and utterance.intent in wanted:
                return utterance
        return None

    def _handle_global_intents(self, utterances: Sequence[Utterance]) -> bool:
        """Handle commands valid in any state. True if the state was handled.

        Returning True skips the state handler for this tick, which is what
        makes "stop" immediate rather than "immediate unless we are busy".
        """
        for utterance in utterances:
            if not utterance.addressed_to_robot:
                continue
            intent = utterance.intent

            if intent == Intent.STOP:
                self._emergency_stop()
                return True
            if intent == Intent.FOLLOW_ME and self.state != RobotState.FOLLOW:
                self._start_following()
                return True
            if intent == Intent.STOP_FOLLOWING and self.state == RobotState.FOLLOW:
                self._stop_following()
                return True
            if intent == Intent.WHAT_DO_YOU_SEE:
                self.dialogue.describe_scene(self.visible_objects())
                return True
            if intent == Intent.WHO_AM_I:
                self.dialogue.identify(self.session.name)
                return True
            if intent == Intent.HELP:
                self.dialogue.describe_capabilities()
                return True
            if intent == Intent.REPEAT:
                self.dialogue.repeat()
                return True
            if intent == Intent.WAKE:
                if self.state is RobotState.WAIT_CONFIRM and utterance.is_affirmative_wake:
                    # "yes buddy" / "yes ANNA" here is consent to start, which
                    # is what the original build did. Let the state handler
                    # act on it instead of swallowing it as a bare wake word.
                    continue
                self.dialogue.acknowledge_wake()
                self.head.nod()
                return True
        return False

    def _emergency_stop(self) -> None:
        """Stop now, and stay stopped for a moment.

        The hold matters: without it the next control tick would see the
        same person and drive straight off again, so "stop" would not have
        meant anything. Any explicit movement command clears it.
        """
        self.motors.stop()
        self.follower.reset()
        self.approach_follower.reset()
        self._drive = DriveCommand(reason="stopped on request")
        self._motion_hold.arm(self.config.emergency_stop_hold_s)
        self.dialogue.warn("Stopping now.")
        if self.state == RobotState.FOLLOW:
            self.state = self._return_state_after_follow

    # -- movement ---------------------------------------------------------
    def _apply_drive(self, command: DriveCommand, dt: float) -> None:
        """Send a follower command to the wheels, with the safety veto."""
        self._drive = command
        if command.state == FollowState.BLOCKED:
            # Safety path: stop now, not over a ramp.
            self.motors.stop()
            return
        if command.linear == 0.0 and command.angular == 0.0:
            self.motors.coast(dt)
            return
        self.motors.drive(command.linear, command.angular, dt)

    def _hold_still(self, dt: float) -> None:
        """Stand still, but keep the last drive state for the overlay."""
        self.motors.stop()
        self._drive = DriveCommand(state=self._drive.state, reason="holding")

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------
    def _step(self, frame: np.ndarray, distance: float, utterances: Sequence[Utterance], dt: float) -> None:
        if not self._motion_hold.expired():
            # Still within the hold from a "stop": stay put, but keep seeing,
            # tracking and listening so a new command is picked up at once.
            self._hold_still(dt)
            return

        handlers = {
            RobotState.STARTUP: self._handle_startup,
            RobotState.SEARCH: self._handle_search,
            RobotState.INTERACT: self._handle_interact,
            RobotState.WAIT_CONFIRM: self._handle_wait_confirm,
            RobotState.HEALTH_CHECK: self._handle_health_check,
            RobotState.FOLLOW: self._handle_follow,
            RobotState.DONE: self._handle_done,
        }
        handlers[self.state](frame, distance, utterances, dt)

    def _handle_startup(self, frame, distance, utterances, dt) -> None:
        self.state = RobotState.SEARCH

    def _handle_search(self, frame, distance, utterances, dt) -> None:
        """Look for a person, then close on them under PID control."""
        target = self.visual_feedback.target
        if target is None or not self.tracker.is_confirmed:
            self.approach_follower.reset()
            self._hold_still(dt)
            return

        # Close enough, and actually in front: greet them.
        near_enough = distance <= self.config.distance_trigger_cm or (
            target.distance_cm is not None and target.distance_cm <= self.config.distance_trigger_cm
        )
        if near_enough:
            self.motors.stop()
            self.approach_follower.reset()
            self.dialogue.say("I can see someone. Let me check if I recognise you.")
            self._enter_interact()
            return

        command = self.approach_follower.update(
            target, dt, obstacle_cm=distance, search_when_lost=False
        )
        if command.state == FollowState.BLOCKED:
            self.dialogue.announce_blocked()
        self._apply_drive(command, dt)

    def _enter_interact(self) -> None:
        self.state = RobotState.INTERACT
        self.greeted = False
        self.unknown_attempts = 0
        self.no_face_count = 0
        self._awaiting_greeting = False
        self._face_check.reset()

    def _handle_interact(self, frame, distance, utterances, dt) -> None:
        """Identify the person in front of ANNA and greet them."""
        self._hold_still(dt)

        # A greeting requested from Gemini arrives here, later, without
        # having blocked the loop while it was generated.
        if self._awaiting_greeting:
            greeting = self.gemini.take_greeting(self.session.name)
            if greeting is not None:
                self._awaiting_greeting = False
                self.dialogue.greet(self.session.name, greeting)
                self.dialogue.invite_health_check()
                self.greeted = True
                self.state = RobotState.WAIT_CONFIRM
                self.router.wake()
            return

        if self.greeted:
            return

        # Face work is throttled: it is by far the most expensive thing in
        # the frame budget, and a face does not move much in 0.4 s.
        if not self._face_check.trigger():
            return

        locations = self.face_identifier.locate(frame)
        self._face_locations = locations
        logger.debug("Faces detected: %d", len(locations))

        if not locations:
            self.no_face_count += 1
            self._face_caption = None
            if self.no_face_count >= self.config.max_no_face_frames:
                self.dialogue.say("I could not find anyone. Resuming search.")
                self._return_to_search()
            return
        self.no_face_count = 0

        if not self.face_identifier.available:
            self.dialogue.say("My face recognition is unavailable, so I cannot identify patients right now.")
            self._return_to_search()
            return
        if not self.face_identifier.has_known_faces:
            logger.info("No known faces stored.")
            self.dialogue.say("No registered patient data is available.")
            self._return_to_search()
            return

        encodings = self.face_identifier.encode(frame, locations, limit=1)
        if not encodings:
            return

        name, best_distance = self.face_identifier.match(encodings[0])
        logger.debug("Best face distance: %.3f", best_distance)
        if name is not None:
            self._on_recognised(frame, locations[0], name)
        else:
            self._on_unknown(best_distance)

    def _on_recognised(self, frame: np.ndarray, location, name: str) -> None:
        face_crop = self.face_identifier.crop(frame, location, margin=0.1)
        self.session.name = name
        self.session.emotion = self.emotion_detector.detect(face_crop)
        self.session.clear_readings()
        self.question_index = 0
        self._face_caption = f"Recognised: {name}"
        logger.info("Recognised %s (emotion=%s)", name, self.session.emotion)

        # Ask Gemini in the background and acknowledge immediately, so there
        # is no dead air while the greeting is generated.
        self.gemini.request_greeting(name, self.session.emotion)
        self._awaiting_greeting = True
        self.dialogue.say(f"Hello {name}.", dedupe=False)

    def _on_unknown(self, best_distance: float) -> None:
        self.unknown_attempts += 1
        self._face_caption = "Unknown face"
        logger.info("Unknown face. attempt=%d distance=%.3f", self.unknown_attempts, best_distance)
        self.dialogue.unknown_person(self.unknown_attempts)
        if self.unknown_attempts >= self.config.max_unknown_attempts:
            self.dialogue.say("I was unable to recognise anyone. Resuming search.")
            self._return_to_search()

    def _return_to_search(self) -> None:
        self.state = RobotState.SEARCH
        self.greeted = False
        self.no_face_count = 0
        self.unknown_attempts = 0
        self._face_locations = []
        self._face_caption = None
        self.tracker.clear()
        self.approach_follower.reset()

    def _handle_wait_confirm(self, frame, distance, utterances, dt) -> None:
        """Wait for the patient to say they are ready."""
        self._hold_still(dt)
        consented = self.first_intent(utterances, Intent.START_HEALTH_CHECK, Intent.YES) is not None
        consented = consented or any(u.is_affirmative_wake for u in utterances)
        if consented:
            self.dialogue.say(
                "Perfect. Let us begin your health check. I will first take some sensor readings "
                "and then ask you a few quick health questions."
            )
            self.health_stage = HealthStage.ASK_TEMP
            self.question_index = 0
            self.state = RobotState.HEALTH_CHECK
        elif self.first_intent(utterances, Intent.NO, Intent.CANCEL) is not None:
            self.dialogue.say("No problem. Say, hey ANNA, start my health check, whenever you are ready.")

    def _handle_health_check(self, frame, distance, utterances, dt) -> None:
        """Work through the readings, the questions and the summary."""
        self._hold_still(dt)

        # Never advance while ANNA is mid-sentence: the patient has not
        # heard the prompt yet, and the microphone would hear her own voice.
        if self.voice.is_speaking:
            return

        stage = self.health_stage
        if stage == HealthStage.ASK_TEMP:
            self.dialogue.ask(
                "First, please place the temperature sensor properly and say, check temperature, when ready."
            )
            self.health_stage = HealthStage.WAIT_TEMP
            self.router.wake()

        elif stage == HealthStage.WAIT_TEMP:
            if self.first_intent(utterances, Intent.CHECK_TEMPERATURE) is not None:
                self.dialogue.say("Taking temperature reading now. Please hold still.")
                self.session.temperature = self.temperature_sensor.read_celsius()
                self.dialogue.say(f"Got it. Temperature recorded as {self.session.temperature}.")
                self.health_stage = HealthStage.ASK_PULSE

        elif stage == HealthStage.ASK_PULSE:
            self.dialogue.ask("Now please attach the pulse sensor and say, check pulse, when ready.")
            self.health_stage = HealthStage.WAIT_PULSE
            self.router.wake()

        elif stage == HealthStage.WAIT_PULSE:
            if self.first_intent(utterances, Intent.CHECK_PULSE) is not None:
                self.dialogue.say("Measuring your pulse.")
                self.session.pulse = self.pulse_sensor.read_bpm()
                self.dialogue.say(f"Pulse recorded as {self.session.pulse}.")
                self.health_stage = HealthStage.ASK_ECG

        elif stage == HealthStage.ASK_ECG:
            self.dialogue.ask("Now please attach the E C G electrodes and say, check ecg, when ready.")
            self.health_stage = HealthStage.WAIT_ECG
            self.router.wake()

        elif stage == HealthStage.WAIT_ECG:
            if self.first_intent(utterances, Intent.CHECK_ECG) is not None:
                self.dialogue.say("Recording your E C G. Please stay still and breathe normally.")
                self.voice.wait_until_idle(timeout=6.0)
                self.session.ecg = self.ecg_sensor.record_and_analyze()
                self.dialogue.say(
                    f"E C G recorded. Result is {self.session.ecg}. Now I have a few quick health "
                    "questions for you. Please answer each one clearly."
                )
                self.health_stage = HealthStage.ASK_QUESTION
                self.question_index = 0

        elif stage == HealthStage.ASK_QUESTION:
            question = question_for(self.question_index)
            if question is not None:
                self.dialogue.ask(question.prompt, key=question.key)
                self.router.wake()  # An answer is expected; stay attentive.
                self.health_stage = HealthStage.WAIT_ANSWER
            else:
                self._request_summary()

        elif stage == HealthStage.WAIT_ANSWER:
            self._collect_answer(utterances)

        elif stage == HealthStage.SUMMARISE:
            self._deliver_summary()

    def _collect_answer(self, utterances: Sequence[Utterance]) -> None:
        """Record a plausible answer; ignore anything that is clearly not one."""
        question = question_for(self.question_index)
        if question is None:
            self.health_stage = HealthStage.ASK_QUESTION
            return
        for utterance in utterances:
            if not utterance.addressed_to_robot:
                continue
            answer = utterance.remainder or utterance.text
            if not looks_like_answer(question, answer):
                # A recognised command here is a command, not an answer.
                if utterance.intent not in (Intent.CHAT, Intent.YES, Intent.NO):
                    continue
            self.session.answers[question.key] = answer
            logger.info("Q: %s | A: %s", question.prompt, answer)
            self.dialogue.confirm_answer()
            self.question_index += 1
            self.health_stage = HealthStage.ASK_QUESTION
            return

    def _request_summary(self) -> None:
        """Kick off the (background) summary generation."""
        self.dialogue.say(
            f"Thank you for answering all my questions, {self.session.name}. "
            "Let me analyse your health data now."
        )
        answers_by_label = {
            question.label: self.session.answers.get(question.key, "not answered")
            for question in HEALTH_QUESTIONS
        }
        self.gemini.request_summaries(
            self.session.name, self.session.temperature, self.session.pulse,
            self.session.ecg, answers_by_label,
        )
        self.health_stage = HealthStage.SUMMARISE

    def _deliver_summary(self) -> None:
        summaries = self.gemini.take_summaries()
        if summaries is None:
            return  # Still generating; the loop keeps running meanwhile.
        self.session.clinical_report, self.session.health_report = summaries
        self.dialogue.say(self.session.health_report, dedupe=False)
        self.dialogue.say(
            f"Your health session is complete. Take care, {self.session.name}. Have a wonderful day."
        )
        self.state = RobotState.DONE
        self._pause.arm(self.config.done_pause_s)

    # -- following --------------------------------------------------------
    def _start_following(self) -> None:
        self._motion_hold.clear()  # An explicit command to move overrides a hold.
        self._return_state_after_follow = (
            self.state if self.state in (RobotState.WAIT_CONFIRM, RobotState.HEALTH_CHECK)
            else RobotState.SEARCH
        )
        self.follower.reset()
        self.state = RobotState.FOLLOW
        self.dialogue.announce_following()

    def _stop_following(self) -> None:
        self.motors.stop()
        self.follower.reset()
        self._drive = DriveCommand()
        self.state = self._return_state_after_follow
        self.dialogue.announce_stopped_following()

    def _handle_follow(self, frame, distance, utterances, dt) -> None:
        """Walk with the person, smoothly, until told to stop."""
        target = self.visual_feedback.target
        command = self.follower.update(target, dt, obstacle_cm=distance, search_when_lost=True)

        if command.state == FollowState.BLOCKED:
            self.dialogue.announce_blocked()
        elif command.state == FollowState.SEARCHING:
            self.dialogue.announce_lost()
        elif command.state == FollowState.IDLE and self.follower.gave_up:
            self.dialogue.say("I have lost you, so I will wait here.")
            self._stop_following()
            return

        self._apply_drive(command, dt)

    def _handle_done(self, frame, distance, utterances, dt) -> None:
        """Pause between patients - without freezing the loop to do it."""
        self._hold_still(dt)
        if not self._pause.expired():
            return
        self._pause.clear()
        self.dialogue.say("Healthcare robot resuming search. Looking for the next patient.")
        self.question_index = 0
        self.session.reset()
        self._return_to_search()

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    def _annotate(self, frame: np.ndarray, distance: float) -> None:
        draw_detections(frame, self._detections)
        if self.state == RobotState.INTERACT and self._face_locations:
            draw_faces(frame, self._face_locations, self._face_caption)
        draw_target(frame, self.visual_feedback.target)
        draw_head(frame, self.head)
        draw_drive(frame, self._drive)
        extras = {"patient": self.session.name} if self.session.is_identified else {}
        if self.router.is_attentive:
            extras["listening"] = f"{self.router.attention_remaining_s():.0f}s"
        draw_status(frame, self.state.value, self._loop.fps, distance, extras)

    def _publish(self, frame: np.ndarray, distance: float) -> None:
        self.telemetry.send(self.session.to_telemetry(distance, self.state.value, self._status_extra()))
        if self.vision_stream:
            self.vision_stream.publish(frame)

    @property
    def active_follower(self) -> PersonFollower:
        """Whichever follower is driving right now (they are separate so
        their integrators never leak state across a mode change)."""
        return self.follower if self.state is RobotState.FOLLOW else self.approach_follower

    def _status_extra(self) -> Dict[str, object]:
        """The new telemetry fields, added alongside the original ones."""
        target = self.visual_feedback.target
        follower = self.active_follower
        return {
            "fps": round(self._loop.fps, 1),
            "camera_fps": round(self.camera.fps, 1),
            "detections": [detection.as_dict() for detection in self._detections],
            "target": None if target is None else target.as_dict(),
            "drive": self._drive.as_dict(),
            "head": self.head.as_dict(),
            "feedback": self.feedback.as_dict(),
            "listening": self.router.is_attentive,
            "speaking": self.voice.is_speaking,
            "health_stage": None if self.health_stage is None else self.health_stage.name,
            "pid": {
                "bearing": follower.bearing_pid.debug.as_dict(),
                "range": follower.range_pid.debug.as_dict(),
            },
        }

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """Stop everything, in the reverse order it was started."""
        logger.info("Shutting down...")
        motors = getattr(self, "motors", None)
        if motors is not None:
            try:
                motors.stop()
            except Exception:
                logger.exception("Error while stopping motors.")

        for resource in reversed(self._built):
            closer = getattr(resource, "close", None) or getattr(resource, "release", None)
            if closer is None:
                continue
            try:
                closer()
            except Exception:
                logger.exception("Error while closing %s.", type(resource).__name__)
        self._built.clear()

        try:
            get_gpio().cleanup()
        except Exception:
            logger.exception("Error during GPIO cleanup.")
        if self.config.show_debug_window:
            try:
                cv2.destroyAllWindows()
            except Exception:
                logger.debug("No debug window to close.", exc_info=True)
