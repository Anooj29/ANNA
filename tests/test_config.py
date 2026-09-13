"""Configuration parsing and the safety validations."""

from __future__ import annotations

import pytest

from anna_robot.config import Config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start each test from a known-empty environment."""
    for name in list(__import__("os").environ):
        if name.startswith("ROBOT_") or name.startswith("GEMINI_"):
            monkeypatch.delenv(name, raising=False)


def test_defaults_are_valid():
    assert Config().validate() == []
    assert Config.from_env().validate() == []


def test_env_overrides_are_applied(monkeypatch):
    monkeypatch.setenv("ROBOT_TCP_PORT", "6000")
    monkeypatch.setenv("ROBOT_TTS_RATE", "200")
    monkeypatch.setenv("ROBOT_SHOW_DEBUG_WINDOW", "false")
    config = Config.from_env()
    assert config.tcp_port == 6000
    assert config.tts_rate == 200
    assert config.show_debug_window is False


def test_camera_indices_are_configurable(monkeypatch):
    """These were silently ignored before, despite being documented."""
    monkeypatch.setenv("ROBOT_CAMERA_INDICES", "2, 0,1")
    assert Config.from_env().camera_indices == (2, 0, 1)


def test_gpio_pins_are_configurable(monkeypatch):
    monkeypatch.setenv("ROBOT_TRIG_PIN", "5")
    monkeypatch.setenv("ROBOT_LEFT_PWM_PIN", "13")
    config = Config.from_env()
    assert config.trig_pin == 5
    assert config.left_pwm_pin == 13


def test_detection_classes_are_configurable(monkeypatch):
    monkeypatch.setenv("ROBOT_DETECTION_CLASSES", "person, bed , chair")
    assert Config.from_env().detection_classes == ("person", "bed", "chair")


def test_head_pins_accept_blank_as_unset(monkeypatch):
    monkeypatch.setenv("ROBOT_HEAD_PAN_PIN", "")
    assert Config.from_env().head_pan_pin is None


def test_a_malformed_value_falls_back_instead_of_crashing(monkeypatch):
    """A typo in .env must not stop the robot from booting."""
    monkeypatch.setenv("ROBOT_TTS_RATE", "fast")
    monkeypatch.setenv("ROBOT_CAMERA_INDICES", "a,b")
    config = Config.from_env()
    assert config.tts_rate == Config().tts_rate
    assert config.camera_indices == Config().camera_indices


def test_booleans_accept_common_spellings(monkeypatch):
    for value in ("1", "true", "YES", "on", "y"):
        monkeypatch.setenv("ROBOT_MIC_ENABLED", value)
        assert Config.from_env().mic_enabled is True
    monkeypatch.setenv("ROBOT_MIC_ENABLED", "0")
    assert Config.from_env().mic_enabled is False


# -- validation ---------------------------------------------------------
def test_a_stop_distance_beyond_the_greeting_distance_is_rejected():
    problems = Config(safety_stop_cm=100.0, distance_trigger_cm=60.0).validate()
    assert any("DISTANCE_TRIGGER" in problem for problem in problems)


def test_a_follow_distance_inside_the_stop_distance_is_rejected():
    problems = Config(safety_stop_cm=100.0, follow_distance_cm=50.0).validate()
    assert any("FOLLOW_DISTANCE" in problem for problem in problems)


def test_head_travel_beyond_a_quarter_turn_is_rejected():
    """Guarding the cable loom: the head must never be able to spin."""
    problems = Config(head_pan_min_deg=-180.0, head_pan_max_deg=180.0).validate()
    assert any("cabling" in problem for problem in problems)


def test_inverted_head_limits_are_rejected():
    problems = Config(head_pan_min_deg=70.0, head_pan_max_deg=-70.0).validate()
    assert any("HEAD_PAN_MIN_DEG" in problem for problem in problems)


def test_one_head_pin_without_the_other_is_rejected():
    problems = Config(head_pan_pin=12, head_tilt_pin=None).validate()
    assert any("HEAD_TILT_PIN" in problem for problem in problems)


def test_two_devices_on_one_pin_are_rejected():
    problems = Config(trig_pin=18, left_pwm_pin=18).validate()
    assert any("more than one device" in problem for problem in problems)


def test_out_of_range_thresholds_are_rejected():
    assert Config(person_detection_threshold=1.5).validate()
    assert Config(face_match_threshold=0.0).validate()
    assert Config(detect_every_n_frames=0).validate()


def test_describe_hides_the_api_key():
    described = Config(gemini_api_key="secret-key-value").describe()
    assert "secret-key-value" not in described
    assert "<set>" in described
