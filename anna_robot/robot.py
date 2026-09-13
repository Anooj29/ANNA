"""Top-level state machine tying together perception, motor control,
sensors, voice and the telemetry link."""

from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np
import RPi.GPIO as GPIO

from .config import Config
from .gemini_assistant import GeminiAssistant
from .motors import MotorController
from .patient_session import PatientSession
from .perception import EmotionDetector, FaceIdentifier, PersonDetector
from .sensors import EcgSensor, SimulatedPulseSensor, TemperatureSensor, UltrasonicSensor
from .state import HEALTH_QUESTIONS, HealthStage, RobotState
from .telemetry import TelemetryLink
from .vision_stream import VisionStream
from .voice import VoiceAssistant

logger = logging.getLogger(__name__)


class HealthcareRobot:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = PatientSession()

        self.state: RobotState = RobotState.STARTUP
        self.health_stage: Optional[HealthStage] = None
        self.question_index = 0
        self.greeted = False
        self.unknown_attempts = 0
        self.person_detect_count = 0
        self.no_face_count = 0

        # Block here waiting for the companion device, same as the original.
        self.telemetry = TelemetryLink(config.tcp_port)

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        self.motors = MotorController(config.left_dir_pin, config.left_pwm_pin, config.right_dir_pin, config.right_pwm_pin)
        self.ultrasonic = UltrasonicSensor(config.trig_pin, config.echo_pin)
        self.temperature_sensor = TemperatureSensor()
        self.pulse_sensor = SimulatedPulseSensor()
        self.ecg_sensor = EcgSensor(config.ecg_lo_plus_pin, config.ecg_lo_minus_pin)

        self.person_detector = PersonDetector(config.person_model_path, config.person_detection_threshold)
        self.face_identifier = FaceIdentifier(config.known_faces_dir, config.face_match_threshold)
        self.emotion_detector = EmotionDetector(config.emotion_model_path)

        self.voice = VoiceAssistant(config.tts_rate, config.reinit_tts_each_call)
        self.gemini = GeminiAssistant(config.gemini_api_key, config.gemini_model)

        self.camera = self._open_camera()
        self.vision_stream = (
            VisionStream(config.vision_stream_host, config.vision_stream_port, config.vision_stream_token)
            if config.vision_stream_enabled else None
        )

    def _open_camera(self) -> cv2.VideoCapture:
        for index in self.config.camera_indices:
            cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
            if cap.isOpened():
                logger.info("Camera opened at index %d.", index)
                return cap
            cap.release()
            logger.warning("Camera index %d failed to open, trying next...", index)
        raise RuntimeError(f"Could not open any camera. Checked indices: {self.config.camera_indices}")

    def run(self) -> None:
        self.voice.speak("Healthcare robot is now active. I am searching for someone I recognise. Please come closer.")
        consecutive_frame_failures = 0
        try:
            while True:
                ok, frame = self.camera.read()
                if not ok:
                    consecutive_frame_failures += 1
                    logger.warning("Frame read failed (%d in a row).", consecutive_frame_failures)
                    if consecutive_frame_failures > 100:
                        raise RuntimeError("Camera stopped returning frames.")
                    time.sleep(0.05)
                    continue
                consecutive_frame_failures = 0

                distance = self.ultrasonic.measure_cm()
                logger.debug("STATE=%s distance=%.1fcm", self.state, distance)

                self.telemetry.send(self.session.to_telemetry(distance, self.state.value))
                command = self.telemetry.receive_command()

                self._step(frame, distance, command)
                if self.vision_stream:
                    self.vision_stream.publish(frame)

                if self.config.show_debug_window:
                    cv2.imshow("Healthcare Robot", frame)
                    if cv2.waitKey(1) == 27:  # Esc quits
                        break
        except KeyboardInterrupt:
            logger.info("Program stopped by user.")
        finally:
            self.shutdown()

    def _step(self, frame: np.ndarray, distance: float, command: str) -> None:
        handlers = {
            RobotState.STARTUP: self._handle_startup,
            RobotState.SEARCH: self._handle_search,
            RobotState.INTERACT: self._handle_interact,
            RobotState.WAIT_CONFIRM: self._handle_wait_confirm,
            RobotState.HEALTH_CHECK: self._handle_health_check,
            RobotState.DONE: self._handle_done,
        }
        handlers[self.state](frame, distance, command)

    def _handle_startup(self, frame: np.ndarray, distance: float, command: str) -> None:
        self.state = RobotState.SEARCH

    def _handle_search(self, frame: np.ndarray, distance: float, command: str) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.person_detector.detect_best(rgb)

        if result is None:
            self.person_detect_count = 0
            self.motors.stop()
            return

        score, (xmin, ymin, xmax, ymax) = result
        cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
        cv2.putText(
            frame, f"Person {score:.2f}", (xmin, max(ymin - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
        )

        self.person_detect_count += 1
        logger.info("Person detected. score=%.2f count=%d", score, self.person_detect_count)

        if self.person_detect_count < self.config.person_confirm_frames:
            self.motors.stop()
            return

        if distance <= self.config.distance_trigger_cm:
            self.motors.stop()
            self.voice.speak("I can see someone. Let me check if I recognise you.")
            self.state = RobotState.INTERACT
            self.greeted = False
            self.unknown_attempts = 0
            self.no_face_count = 0
            self.person_detect_count = 0
            return

        frame_width = frame.shape[1]
        person_center = (xmin + xmax) // 2
        frame_center = frame_width // 2
        margin = 70

        if distance <= self.config.safety_stop_cm:
            self.motors.stop()
        elif person_center < frame_center - margin:
            self.motors.turn_left()
        elif person_center > frame_center + margin:
            self.motors.turn_right()
        else:
            self.motors.forward()

    def _handle_interact(self, frame: np.ndarray, distance: float, command: str) -> None:
        self.motors.stop()

        locations, encodings = self.face_identifier.locate_and_encode(frame)
        logger.debug("Faces detected: %d", len(locations))

        # These are intentionally drawn on the same frame sent to the vision
        # dashboard, so staff see the robot's actual perception output.
        for top, right, bottom, left in locations:
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 191, 255), 2)
            cv2.putText(frame, "Face", (left, max(top - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 191, 255), 2)

        if not encodings:
            self.no_face_count += 1
            if self.no_face_count >= self.config.max_no_face_frames:
                self.voice.speak("I could not find anyone. Resuming search.")
                self.state = RobotState.SEARCH
                self.greeted = False
                self.no_face_count = 0
            return

        self.no_face_count = 0
        if self.greeted:
            return

        if not self.face_identifier.has_known_faces:
            logger.info("No known faces stored.")
            self.voice.speak("No registered patient data is available.")
            self.state = RobotState.SEARCH
            self.greeted = False
            return

        top, right, bottom, left = locations[0]
        face_crop = frame[max(top, 0):bottom, max(left, 0):right]
        encoding = encodings[0]

        name, best_distance = self.face_identifier.match(encoding)
        logger.debug("Best face distance: %.3f", best_distance)

        if name is not None:
            cv2.putText(frame, f"Recognised: {name}", (left, min(bottom + 24, frame.shape[0] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 191, 255), 2)
            self.session.name = name
            self.session.emotion = self.emotion_detector.detect(face_crop)
            self.session.answers = {}
            self.question_index = 0
            self.session.health_report = "--"
            self.session.temperature = self.session.pulse = self.session.ecg = "--"

            logger.info("Recognised %s (emotion=%s)", name, self.session.emotion)

            greeting = self.gemini.emotion_greeting(name, self.session.emotion)
            self.voice.speak(greeting)
            time.sleep(0.5)
            self.voice.speak("Whenever you are ready, say yes buddy to start your health check.")
            self.greeted = True
            self.state = RobotState.WAIT_CONFIRM
            return

        self.unknown_attempts += 1
        cv2.putText(frame, "Unknown face", (left, min(bottom + 24, frame.shape[0] - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 191, 255), 2)
        logger.info("Unknown face. attempt=%d distance=%.3f", self.unknown_attempts, best_distance)

        unknown_responses = [
            "Sorry, I do not recognise you. I am only authorised to assist registered patients.",
            "I am afraid I cannot identify you. Please register with the healthcare system first.",
            "Hmm, your face is not in my database. Please contact the administrator to register.",
        ]
        self.voice.speak(unknown_responses[(self.unknown_attempts - 1) % len(unknown_responses)])

        if self.unknown_attempts >= self.config.max_unknown_attempts:
            self.voice.speak("I was unable to recognise anyone. Resuming search.")
            self.state = RobotState.SEARCH
            self.greeted = False

    def _handle_wait_confirm(self, frame: np.ndarray, distance: float, command: str) -> None:
        self.motors.stop()
        if "yes buddy" in command:
            self.voice.speak(
                "Perfect. Let us begin your health check. I will first take some sensor readings "
                "and then ask you a few quick health questions."
            )
            self.health_stage = HealthStage.ASK_TEMP
            self.question_index = 0
            self.state = RobotState.HEALTH_CHECK

    def _handle_health_check(self, frame: np.ndarray, distance: float, command: str) -> None:
        self.motors.stop()
        stage = self.health_stage

        if stage == HealthStage.ASK_TEMP:
            self.voice.speak("First, please place the temperature sensor properly and say check temperature when ready.")
            self.health_stage = HealthStage.WAIT_TEMP

        elif stage == HealthStage.WAIT_TEMP and "check temperature" in command:
            self.voice.speak("Taking temperature reading now. Please hold still.")
            self.session.temperature = self.temperature_sensor.read_celsius()
            self.voice.speak(f"Got it. Temperature recorded as {self.session.temperature}.")
            self.health_stage = HealthStage.ASK_PULSE

        elif stage == HealthStage.ASK_PULSE:
            self.voice.speak("Now please attach the pulse sensor and say check pulse when ready.")
            self.health_stage = HealthStage.WAIT_PULSE

        elif stage == HealthStage.WAIT_PULSE and "check pulse" in command:
            self.voice.speak("Measuring your pulse.")
            self.session.pulse = self.pulse_sensor.read_bpm()
            self.voice.speak(f"Pulse recorded as {self.session.pulse}.")
            self.health_stage = HealthStage.ASK_ECG

        elif stage == HealthStage.ASK_ECG:
            self.voice.speak("Now please attach the ECG electrodes and say check ecg when ready.")
            self.health_stage = HealthStage.WAIT_ECG

        elif stage == HealthStage.WAIT_ECG and "check ecg" in command:
            self.voice.speak("Recording your ECG. Please stay still and breathe normally.")
            self.session.ecg = self.ecg_sensor.record_and_analyze()
            self.voice.speak(
                f"ECG recorded successfully. Result is {self.session.ecg}. Now I have a few quick health "
                "questions for you. Please answer each one clearly."
            )
            self.health_stage = HealthStage.ASK_QUESTION
            self.question_index = 0

        elif stage == HealthStage.ASK_QUESTION:
            if self.question_index < len(HEALTH_QUESTIONS):
                question = HEALTH_QUESTIONS[self.question_index]
                self.voice.speak(question.prompt)
                self.health_stage = HealthStage.WAIT_ANSWER
            else:
                self.voice.speak(
                    f"Thank you for answering all my questions, {self.session.name}. Let me analyse your health data now."
                )
                answers_by_label = {
                    question.label: self.session.answers.get(question.key, "not answered")
                    for question in HEALTH_QUESTIONS
                }
                self.session.clinical_report, self.session.health_report = self.gemini.health_summaries(
                    self.session.name, self.session.temperature, self.session.pulse, self.session.ecg, answers_by_label
                )
                self.voice.speak(self.session.health_report)
                self.voice.speak(f"Your health session is complete. Take care, {self.session.name}. Have a wonderful day.")
                self.state = RobotState.DONE

        elif stage == HealthStage.WAIT_ANSWER:
            if command:
                question = HEALTH_QUESTIONS[self.question_index]
                self.session.answers[question.key] = command
                logger.info("Q: %s | A: %s", question.prompt, command)
                self.voice.speak("Thank you.")
                self.question_index += 1
                self.health_stage = HealthStage.ASK_QUESTION

    def _handle_done(self, frame: np.ndarray, distance: float, command: str) -> None:
        self.motors.stop()
        time.sleep(10)
        self.voice.speak("Healthcare robot resuming search. Looking for the next patient.")
        self.state = RobotState.SEARCH
        self.greeted = False
        self.question_index = 0
        self.session.reset()

    def shutdown(self) -> None:
        logger.info("Shutting down...")
        try:
            self.motors.stop()
        except Exception:
            logger.exception("Error while stopping motors.")
        try:
            self.camera.release()
        except Exception:
            logger.exception("Error while releasing the camera.")
        if self.vision_stream:
            try:
                self.vision_stream.close()
            except Exception:
                logger.exception("Error while closing the vision stream.")
        try:
            self.telemetry.close()
        except Exception:
            logger.exception("Error while closing the telemetry link.")
        try:
            GPIO.cleanup()
        except Exception:
            logger.exception("Error during GPIO cleanup.")
        if self.config.show_debug_window:
            cv2.destroyAllWindows()
