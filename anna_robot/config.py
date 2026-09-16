"""Central, environment-driven configuration for the robot.

Every field below can be set from the environment, which was the intent of
the original design but only half-implemented - camera indices, GPIO pins,
motor tuning and the control gains were silently ignored. They are all
honoured now.

Parsing is forgiving on purpose: a malformed value logs a clear warning and
falls back to the default instead of crashing the robot at boot, and
:meth:`Config.validate` catches the settings that are genuinely unsafe (a
safety distance larger than the follow distance, say) before anything moves.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, fields
from typing import List, Optional, Tuple

from .perception.labels import DEFAULT_CLASSES_OF_INTEREST

logger = logging.getLogger(__name__)


def env_str(name: str, default: Optional[str]) -> Optional[str]:
    value = os.environ.get(name)
    return default if value is None else value


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using the default %s.", name, raw, default)
        return default


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(float(raw))
    except ValueError:
        logger.warning("%s=%r is not an integer; using the default %s.", name, raw, default)
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def env_int_tuple(name: str, default: Tuple[int, ...]) -> Tuple[int, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    except ValueError:
        logger.warning("%s=%r is not a comma-separated integer list; using %s.", name, raw, default)
        return default
    return values or default


def env_optional_int(name: str, default: Optional[int]) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using the default %s.", name, raw, default)
        return default


def env_str_list(name: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or default


@dataclass
class Config:
    """All robot settings in one place. See README.md for the env var table."""

    # -- assistant --------------------------------------------------------
    gemini_api_key: Optional[str] = None
    gemini_model: str = "models/gemini-flash-latest"
    gemini_timeout_s: float = 12.0

    # -- companion link ---------------------------------------------------
    tcp_port: int = 5000
    tcp_wait_for_client: bool = True
    tcp_connect_timeout_s: Optional[float] = None

    # -- behaviour thresholds --------------------------------------------
    distance_trigger_cm: float = 60.0
    safety_stop_cm: float = 20.0
    person_detection_threshold: float = 0.65
    face_match_threshold: float = 0.45
    person_confirm_frames: int = 3
    max_unknown_attempts: int = 3
    max_no_face_frames: int = 150
    done_pause_s: float = 10.0
    #: How long "stop" keeps the robot still before it may drive again.
    emergency_stop_hold_s: float = 5.0

    # -- models and data --------------------------------------------------
    person_model_path: str = "models/person_detect.tflite"
    emotion_model_path: str = "models/emotion_model.tflite"
    label_map_path: Optional[str] = None
    known_faces_dir: str = "known_faces"
    detection_classes: Tuple[str, ...] = DEFAULT_CLASSES_OF_INTEREST
    detect_every_n_frames: int = 2
    face_check_interval_s: float = 0.4
    face_detection_scale: float = 0.5
    inference_threads: int = 2

    # -- speech -----------------------------------------------------------
    tts_rate: int = 145
    tts_volume: float = 1.0
    tts_voice_id: Optional[str] = None
    reinit_tts_each_call: bool = True
    wake_attention_window_s: float = 12.0
    require_wake_word: bool = False
    mic_enabled: bool = False
    mic_device_index: Optional[int] = None
    mic_device_name: Optional[str] = None
    mic_sample_rate: Optional[int] = None
    mic_language: str = "en-US"

    # -- vision output ----------------------------------------------------
    show_debug_window: bool = True
    vision_stream_enabled: bool = True
    vision_stream_host: str = "0.0.0.0"
    vision_stream_port: int = 8080
    vision_stream_token: Optional[str] = None
    vision_stream_fps: float = 15.0
    vision_stream_quality: int = 80

    # -- camera -----------------------------------------------------------
    camera_indices: Tuple[int, ...] = (0, 1)
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    camera_use_mjpg: bool = True
    control_loop_fps: float = 20.0

    # -- following --------------------------------------------------------
    follow_distance_cm: float = 90.0
    follow_hold_band_cm: float = 18.0
    follow_max_linear: float = 0.5
    follow_max_angular: float = 0.65
    follow_search_timeout_s: float = 8.0
    bearing_kp: float = 0.85
    bearing_ki: float = 0.05
    bearing_kd: float = 0.12
    range_kp: float = 1.30
    range_ki: float = 0.10
    range_kd: float = 0.15

    # -- drive base -------------------------------------------------------
    motor_min_duty: float = 22.0
    motor_max_duty: float = 55.0
    motor_ramp_duty_per_s: float = 60.0
    motor_allow_reverse: bool = False

    # -- head (two servos) ------------------------------------------------
    head_enabled: bool = True
    head_pan_pin: Optional[int] = None
    head_tilt_pin: Optional[int] = None
    head_pan_min_deg: float = -70.0
    head_pan_max_deg: float = 70.0
    head_tilt_min_deg: float = -30.0
    head_tilt_max_deg: float = 30.0
    head_pan_speed_deg_s: float = 120.0
    head_tilt_speed_deg_s: float = 90.0
    head_invert_pan: bool = False
    head_invert_tilt: bool = False
    head_recenter_after_s: float = 3.0

    # -- future feedback segments (off until the hardware exists) --------
    encoder_enabled: bool = False
    encoder_left_pin: Optional[int] = None
    encoder_right_pin: Optional[int] = None
    encoder_ticks_per_rev: int = 20
    wheel_diameter_m: float = 0.065
    wheel_base_m: float = 0.20
    imu_enabled: bool = False

    # -- GPIO pin map (BCM numbering) ------------------------------------
    trig_pin: int = 23
    echo_pin: int = 24
    left_dir_pin: int = 17
    left_pwm_pin: int = 18
    right_dir_pin: int = 22
    right_pwm_pin: int = 27
    ecg_lo_plus_pin: int = 5
    ecg_lo_minus_pin: int = 6

    # -- runtime ----------------------------------------------------------
    simulate_hardware: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        """Build a config from the environment, falling back to defaults."""
        defaults = cls()
        return cls(
            gemini_api_key=os.environ.get("GEMINI_API_KEY"),
            gemini_model=env_str("GEMINI_MODEL", defaults.gemini_model),
            gemini_timeout_s=env_float("ROBOT_GEMINI_TIMEOUT_S", defaults.gemini_timeout_s),

            tcp_port=env_int("ROBOT_TCP_PORT", defaults.tcp_port),
            tcp_wait_for_client=env_bool("ROBOT_TCP_WAIT_FOR_CLIENT", defaults.tcp_wait_for_client),
            tcp_connect_timeout_s=(
                env_float("ROBOT_TCP_CONNECT_TIMEOUT_S", 0.0) or None
            ),

            distance_trigger_cm=env_float("ROBOT_DISTANCE_TRIGGER_CM", defaults.distance_trigger_cm),
            safety_stop_cm=env_float("ROBOT_SAFETY_STOP_CM", defaults.safety_stop_cm),
            person_detection_threshold=env_float("ROBOT_PERSON_THRESHOLD", defaults.person_detection_threshold),
            face_match_threshold=env_float("ROBOT_FACE_MATCH_THRESHOLD", defaults.face_match_threshold),
            person_confirm_frames=env_int("ROBOT_PERSON_CONFIRM_FRAMES", defaults.person_confirm_frames),
            max_unknown_attempts=env_int("ROBOT_MAX_UNKNOWN_ATTEMPTS", defaults.max_unknown_attempts),
            max_no_face_frames=env_int("ROBOT_MAX_NO_FACE_FRAMES", defaults.max_no_face_frames),
            done_pause_s=env_float("ROBOT_DONE_PAUSE_S", defaults.done_pause_s),
            emergency_stop_hold_s=env_float("ROBOT_STOP_HOLD_S", defaults.emergency_stop_hold_s),

            person_model_path=env_str("ROBOT_PERSON_MODEL", defaults.person_model_path),
            emotion_model_path=env_str("ROBOT_EMOTION_MODEL", defaults.emotion_model_path),
            label_map_path=env_str("ROBOT_LABEL_MAP", defaults.label_map_path),
            known_faces_dir=env_str("ROBOT_KNOWN_FACES_DIR", defaults.known_faces_dir),
            detection_classes=env_str_list("ROBOT_DETECTION_CLASSES", defaults.detection_classes),
            detect_every_n_frames=env_int("ROBOT_DETECT_EVERY_N_FRAMES", defaults.detect_every_n_frames),
            face_check_interval_s=env_float("ROBOT_FACE_CHECK_INTERVAL_S", defaults.face_check_interval_s),
            face_detection_scale=env_float("ROBOT_FACE_DETECTION_SCALE", defaults.face_detection_scale),
            inference_threads=env_int("ROBOT_INFERENCE_THREADS", defaults.inference_threads),

            tts_rate=env_int("ROBOT_TTS_RATE", defaults.tts_rate),
            tts_volume=env_float("ROBOT_TTS_VOLUME", defaults.tts_volume),
            tts_voice_id=env_str("ROBOT_TTS_VOICE", defaults.tts_voice_id),
            reinit_tts_each_call=env_bool("ROBOT_TTS_REINIT_EACH_CALL", defaults.reinit_tts_each_call),
            wake_attention_window_s=env_float("ROBOT_WAKE_WINDOW_S", defaults.wake_attention_window_s),
            require_wake_word=env_bool("ROBOT_REQUIRE_WAKE_WORD", defaults.require_wake_word),
            mic_enabled=env_bool("ROBOT_MIC_ENABLED", defaults.mic_enabled),
            mic_device_index=env_optional_int("ROBOT_MIC_DEVICE_INDEX", defaults.mic_device_index),
            mic_device_name=env_str("ROBOT_MIC_DEVICE_NAME", defaults.mic_device_name),
            mic_sample_rate=env_optional_int("ROBOT_MIC_SAMPLE_RATE", defaults.mic_sample_rate),
            mic_language=env_str("ROBOT_MIC_LANGUAGE", defaults.mic_language),

            show_debug_window=env_bool("ROBOT_SHOW_DEBUG_WINDOW", defaults.show_debug_window),
            vision_stream_enabled=env_bool("ROBOT_VISION_STREAM_ENABLED", defaults.vision_stream_enabled),
            vision_stream_host=env_str("ROBOT_VISION_STREAM_HOST", defaults.vision_stream_host),
            vision_stream_port=env_int("ROBOT_VISION_STREAM_PORT", defaults.vision_stream_port),
            vision_stream_token=os.environ.get("ROBOT_VISION_STREAM_TOKEN") or None,
            vision_stream_fps=env_float("ROBOT_VISION_STREAM_FPS", defaults.vision_stream_fps),
            vision_stream_quality=env_int("ROBOT_VISION_STREAM_QUALITY", defaults.vision_stream_quality),

            camera_indices=env_int_tuple("ROBOT_CAMERA_INDICES", defaults.camera_indices),
            camera_width=env_int("ROBOT_CAMERA_WIDTH", defaults.camera_width),
            camera_height=env_int("ROBOT_CAMERA_HEIGHT", defaults.camera_height),
            camera_fps=env_int("ROBOT_CAMERA_FPS", defaults.camera_fps),
            camera_use_mjpg=env_bool("ROBOT_CAMERA_MJPG", defaults.camera_use_mjpg),
            control_loop_fps=env_float("ROBOT_CONTROL_LOOP_FPS", defaults.control_loop_fps),

            follow_distance_cm=env_float("ROBOT_FOLLOW_DISTANCE_CM", defaults.follow_distance_cm),
            follow_hold_band_cm=env_float("ROBOT_FOLLOW_HOLD_BAND_CM", defaults.follow_hold_band_cm),
            follow_max_linear=env_float("ROBOT_FOLLOW_MAX_LINEAR", defaults.follow_max_linear),
            follow_max_angular=env_float("ROBOT_FOLLOW_MAX_ANGULAR", defaults.follow_max_angular),
            follow_search_timeout_s=env_float("ROBOT_FOLLOW_SEARCH_TIMEOUT_S", defaults.follow_search_timeout_s),
            bearing_kp=env_float("ROBOT_BEARING_KP", defaults.bearing_kp),
            bearing_ki=env_float("ROBOT_BEARING_KI", defaults.bearing_ki),
            bearing_kd=env_float("ROBOT_BEARING_KD", defaults.bearing_kd),
            range_kp=env_float("ROBOT_RANGE_KP", defaults.range_kp),
            range_ki=env_float("ROBOT_RANGE_KI", defaults.range_ki),
            range_kd=env_float("ROBOT_RANGE_KD", defaults.range_kd),

            motor_min_duty=env_float("ROBOT_MOTOR_MIN_DUTY", defaults.motor_min_duty),
            motor_max_duty=env_float("ROBOT_MOTOR_MAX_DUTY", defaults.motor_max_duty),
            motor_ramp_duty_per_s=env_float("ROBOT_MOTOR_RAMP_DUTY_PER_S", defaults.motor_ramp_duty_per_s),
            motor_allow_reverse=env_bool("ROBOT_MOTOR_ALLOW_REVERSE", defaults.motor_allow_reverse),

            head_enabled=env_bool("ROBOT_HEAD_ENABLED", defaults.head_enabled),
            head_pan_pin=env_optional_int("ROBOT_HEAD_PAN_PIN", defaults.head_pan_pin),
            head_tilt_pin=env_optional_int("ROBOT_HEAD_TILT_PIN", defaults.head_tilt_pin),
            head_pan_min_deg=env_float("ROBOT_HEAD_PAN_MIN_DEG", defaults.head_pan_min_deg),
            head_pan_max_deg=env_float("ROBOT_HEAD_PAN_MAX_DEG", defaults.head_pan_max_deg),
            head_tilt_min_deg=env_float("ROBOT_HEAD_TILT_MIN_DEG", defaults.head_tilt_min_deg),
            head_tilt_max_deg=env_float("ROBOT_HEAD_TILT_MAX_DEG", defaults.head_tilt_max_deg),
            head_pan_speed_deg_s=env_float("ROBOT_HEAD_PAN_SPEED_DEG_S", defaults.head_pan_speed_deg_s),
            head_tilt_speed_deg_s=env_float("ROBOT_HEAD_TILT_SPEED_DEG_S", defaults.head_tilt_speed_deg_s),
            head_invert_pan=env_bool("ROBOT_HEAD_INVERT_PAN", defaults.head_invert_pan),
            head_invert_tilt=env_bool("ROBOT_HEAD_INVERT_TILT", defaults.head_invert_tilt),
            head_recenter_after_s=env_float("ROBOT_HEAD_RECENTER_AFTER_S", defaults.head_recenter_after_s),

            encoder_enabled=env_bool("ROBOT_ENCODER_ENABLED", defaults.encoder_enabled),
            encoder_left_pin=env_optional_int("ROBOT_ENCODER_LEFT_PIN", defaults.encoder_left_pin),
            encoder_right_pin=env_optional_int("ROBOT_ENCODER_RIGHT_PIN", defaults.encoder_right_pin),
            encoder_ticks_per_rev=env_int("ROBOT_ENCODER_TICKS_PER_REV", defaults.encoder_ticks_per_rev),
            wheel_diameter_m=env_float("ROBOT_WHEEL_DIAMETER_M", defaults.wheel_diameter_m),
            wheel_base_m=env_float("ROBOT_WHEEL_BASE_M", defaults.wheel_base_m),
            imu_enabled=env_bool("ROBOT_IMU_ENABLED", defaults.imu_enabled),

            trig_pin=env_int("ROBOT_TRIG_PIN", defaults.trig_pin),
            echo_pin=env_int("ROBOT_ECHO_PIN", defaults.echo_pin),
            left_dir_pin=env_int("ROBOT_LEFT_DIR_PIN", defaults.left_dir_pin),
            left_pwm_pin=env_int("ROBOT_LEFT_PWM_PIN", defaults.left_pwm_pin),
            right_dir_pin=env_int("ROBOT_RIGHT_DIR_PIN", defaults.right_dir_pin),
            right_pwm_pin=env_int("ROBOT_RIGHT_PWM_PIN", defaults.right_pwm_pin),
            ecg_lo_plus_pin=env_int("ROBOT_ECG_LO_PLUS_PIN", defaults.ecg_lo_plus_pin),
            ecg_lo_minus_pin=env_int("ROBOT_ECG_LO_MINUS_PIN", defaults.ecg_lo_minus_pin),

            simulate_hardware=env_bool("ROBOT_SIMULATE_HARDWARE", defaults.simulate_hardware),
        )

    # -- validation -------------------------------------------------------
    def validate(self) -> List[str]:
        """Return a list of problems. Empty means the config is safe to run.

        These are the mistakes that would otherwise show up as odd behaviour
        on the floor rather than as an error message.
        """
        problems: List[str] = []

        if self.safety_stop_cm <= 0:
            problems.append("ROBOT_SAFETY_STOP_CM must be positive.")
        if self.distance_trigger_cm <= self.safety_stop_cm:
            problems.append(
                "ROBOT_DISTANCE_TRIGGER_CM must be greater than ROBOT_SAFETY_STOP_CM, "
                "or the robot would stop before it ever reached greeting distance."
            )
        if self.follow_distance_cm <= self.safety_stop_cm:
            problems.append(
                "ROBOT_FOLLOW_DISTANCE_CM must be greater than ROBOT_SAFETY_STOP_CM."
            )
        if not 0.0 < self.person_detection_threshold < 1.0:
            problems.append("ROBOT_PERSON_THRESHOLD must be between 0 and 1.")
        if not 0.0 < self.face_match_threshold < 1.0:
            problems.append("ROBOT_FACE_MATCH_THRESHOLD must be between 0 and 1.")
        if self.detect_every_n_frames < 1:
            problems.append("ROBOT_DETECT_EVERY_N_FRAMES must be at least 1.")
        if not 0.1 <= self.face_detection_scale <= 1.0:
            problems.append("ROBOT_FACE_DETECTION_SCALE must be between 0.1 and 1.0.")
        if self.motor_min_duty >= self.motor_max_duty:
            problems.append("ROBOT_MOTOR_MIN_DUTY must be below ROBOT_MOTOR_MAX_DUTY.")
        if self.head_pan_min_deg >= self.head_pan_max_deg:
            problems.append("ROBOT_HEAD_PAN_MIN_DEG must be below ROBOT_HEAD_PAN_MAX_DEG.")
        if self.head_tilt_min_deg >= self.head_tilt_max_deg:
            problems.append("ROBOT_HEAD_TILT_MIN_DEG must be below ROBOT_HEAD_TILT_MAX_DEG.")
        if max(abs(self.head_pan_min_deg), abs(self.head_pan_max_deg)) > 90.0:
            problems.append(
                "Head pan travel must stay within +/-90 degrees - the head carries the "
                "camera cabling and must never be able to rotate freely."
            )
        if max(abs(self.head_tilt_min_deg), abs(self.head_tilt_max_deg)) > 90.0:
            problems.append("Head tilt travel must stay within +/-90 degrees.")
        if self.head_enabled and (self.head_pan_pin is None) != (self.head_tilt_pin is None):
            problems.append(
                "Head tracking needs both ROBOT_HEAD_PAN_PIN and ROBOT_HEAD_TILT_PIN, or neither."
            )
        if self.control_loop_fps < 0:
            problems.append("ROBOT_CONTROL_LOOP_FPS cannot be negative.")

        duplicate = self._duplicate_pins()
        if duplicate:
            problems.append(f"These GPIO pins are assigned to more than one device: {duplicate}.")
        return problems

    def _duplicate_pins(self) -> List[int]:
        """Catch two devices wired to the same pin - a silent, baffling fault."""
        pin_fields = [
            self.trig_pin, self.echo_pin, self.left_dir_pin, self.left_pwm_pin,
            self.right_dir_pin, self.right_pwm_pin, self.ecg_lo_plus_pin, self.ecg_lo_minus_pin,
            self.head_pan_pin, self.head_tilt_pin, self.encoder_left_pin, self.encoder_right_pin,
        ]
        used = [pin for pin in pin_fields if pin is not None]
        return sorted({pin for pin in used if used.count(pin) > 1})

    def describe(self) -> str:
        """A one-line-per-setting dump, logged at DEBUG on startup."""
        lines = []
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "gemini_api_key":
                value = "<set>" if value else "<unset>"
            lines.append(f"  {item.name} = {value}")
        return "Robot configuration:\n" + "\n".join(lines)
