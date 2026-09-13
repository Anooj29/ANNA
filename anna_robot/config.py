"""Central, environment-driven configuration for the robot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple
from pathlib import Path

@dataclass
class Config:
    gemini_api_key: Optional[str] = None
    gemini_model: str = "models/gemini-flash-latest"

    tcp_port: int = 5000

    distance_trigger_cm: float = 60.0
    safety_stop_cm: float = 20.0
    person_detection_threshold: float = 0.65
    face_match_threshold: float = 0.45
    person_confirm_frames: int = 3
    max_unknown_attempts: int = 3
    max_no_face_frames: int = 150

    person_model_path: str = "models/person_detect.tflite"
    emotion_model_path: str = "models/emotion_model.tflite"
    known_faces_dir: str = "known_faces"
    sessions_dir: str = "sessions"

    # Voice / Speech
    tts_rate: int = 145
    reinit_tts_each_call: bool = True
    vosk_model_path: str = str(Path.home() / "dishant/models/vosk-model-small-en-us-0.15")
    piper_bin_path: str = str(Path.home() / "dishant/piper/piper/piper")
    piper_model_path: str = str(Path.home() / "dishant/voices/en_US-lessac-low.onnx")

    show_debug_window: bool = True

    camera_indices: Tuple[int, ...] = (0, 1)

    trig_pin: int = 23
    echo_pin: int = 24
    left_dir_pin: int = 17
    left_pwm_pin: int = 18
    right_dir_pin: int = 22
    right_pwm_pin: int = 27
    ecg_lo_plus_pin: int = 5
    ecg_lo_minus_pin: int = 6

    @classmethod
    def from_env(cls) -> "Config":
        def _float(name: str, default: float) -> float:
            return float(os.environ.get(name, default))

        def _int(name: str, default: int) -> int:
            return int(os.environ.get(name, default))

        def _bool(name: str, default: bool) -> bool:
            raw = os.environ.get(name)
            return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")

        return cls(
            gemini_api_key=os.environ.get("GEMINI_API_KEY"),
            gemini_model=os.environ.get("GEMINI_MODEL", cls.gemini_model),
            tcp_port=_int("ROBOT_TCP_PORT", cls.tcp_port),
            distance_trigger_cm=_float("ROBOT_DISTANCE_TRIGGER_CM", cls.distance_trigger_cm),
            safety_stop_cm=_float("ROBOT_SAFETY_STOP_CM", cls.safety_stop_cm),
            person_detection_threshold=_float("ROBOT_PERSON_THRESHOLD", cls.person_detection_threshold),
            face_match_threshold=_float("ROBOT_FACE_MATCH_THRESHOLD", cls.face_match_threshold),
            person_confirm_frames=_int("ROBOT_PERSON_CONFIRM_FRAMES", cls.person_confirm_frames),
            max_unknown_attempts=_int("ROBOT_MAX_UNKNOWN_ATTEMPTS", cls.max_unknown_attempts),
            max_no_face_frames=_int("ROBOT_MAX_NO_FACE_FRAMES", cls.max_no_face_frames),
            person_model_path=os.environ.get("ROBOT_PERSON_MODEL", cls.person_model_path),
            emotion_model_path=os.environ.get("ROBOT_EMOTION_MODEL", cls.emotion_model_path),
            known_faces_dir=os.environ.get("ROBOT_KNOWN_FACES_DIR", cls.known_faces_dir),
            sessions_dir=os.environ.get("ROBOT_SESSIONS_DIR", cls.sessions_dir),
            tts_rate=_int("ROBOT_TTS_RATE", cls.tts_rate),
            reinit_tts_each_call=_bool("ROBOT_TTS_REINIT_EACH_CALL", cls.reinit_tts_each_call),
            vosk_model_path=os.environ.get("ROBOT_VOSK_MODEL", cls.vosk_model_path),
            piper_bin_path=os.environ.get("ROBOT_PIPER_BIN", cls.piper_bin_path),
            piper_model_path=os.environ.get("ROBOT_PIPER_MODEL", cls.piper_model_path),
            show_debug_window=_bool("ROBOT_SHOW_DEBUG_WINDOW", cls.show_debug_window),
        )
