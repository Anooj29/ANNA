"""Emotion detection degrades instead of failing."""

from __future__ import annotations

import numpy as np

from anna_robot.perception.emotion_detector import EmotionDetector, NullEmotionDetector


def test_a_missing_model_falls_back_instead_of_stopping_the_robot():
    detector = EmotionDetector.load_or_null("/nowhere/emotion.tflite")
    assert isinstance(detector, NullEmotionDetector)
    assert detector.available is False
    assert detector.detect(np.zeros((64, 64, 3), np.uint8)) == "Neutral"


def test_the_null_detector_handles_an_empty_crop():
    assert NullEmotionDetector().detect(np.empty((0, 0, 3), np.uint8)) == "Neutral"
