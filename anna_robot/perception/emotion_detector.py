"""TFLite facial-emotion recognition.

Two fixes over the original prototype:

* It is fed a *cropped face* (as produced by the face bounding boxes) rather
  than the whole camera frame, which is what makes the result meaningful.
* Input handling follows the model's own tensor spec - colour or greyscale,
  float or quantised - instead of assuming a float greyscale model and
  silently producing nonsense on any other export.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .tflite_backend import dequantize, input_scaling, load_interpreter_factory, quantize

logger = logging.getLogger(__name__)


class NullEmotionDetector:
    """Stand-in used when the emotion model is missing or unreadable.

    Emotion only colours the greeting, so losing it must never stop ANNA
    from finding and identifying a patient.
    """

    available = False
    last_confidence = 0.0

    def detect(self, face_bgr) -> str:
        return "Neutral"


class EmotionDetector:
    available = True
    LABELS: Tuple[str, ...] = ("Angry", "Disgust", "Fear", "Happy", "Neutral", "Sad", "Surprise")
    NEUTRAL = "Neutral"

    def __init__(self, model_path: str, labels: Optional[List[str]] = None, num_threads: int = 1) -> None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Emotion model not found at '{model_path}'. See models/README.md for where to get one."
            )
        interpreter_factory = load_interpreter_factory()
        try:
            self._interpreter = interpreter_factory(model_path=model_path, num_threads=max(int(num_threads), 1))
        except TypeError:
            self._interpreter = interpreter_factory(model_path=model_path)
        self._interpreter.allocate_tensors()

        self._input_detail = self._interpreter.get_input_details()[0]
        self._output_detail = self._interpreter.get_output_details()[0]
        shape = list(self._input_detail["shape"])
        self._input_h, self._input_w = int(shape[1]), int(shape[2])
        self._channels = int(shape[3]) if len(shape) > 3 else 1
        self._mean, self._std = input_scaling(self._input_detail)
        self.labels = tuple(labels) if labels else self.LABELS

        output_size = int(self._output_detail["shape"][-1])
        if output_size != len(self.labels):
            # Guarding here means a mismatched model degrades to "unknown"
            # instead of raising IndexError in the middle of a greeting.
            logger.warning(
                "Emotion model outputs %d classes but %d labels are configured; "
                "results outside the label list will be reported as '%s'.",
                output_size, len(self.labels), self.NEUTRAL,
            )
        self.last_confidence = 0.0

    @classmethod
    def load_or_null(cls, model_path: str, **kwargs):
        """Load the model, or fall back to a neutral stand-in."""
        try:
            return cls(model_path, **kwargs)
        except Exception as exc:
            logger.warning(
                "Emotion detection is unavailable (%s); greetings will use a neutral tone. "
                "Everything else works as normal.", exc,
            )
            return NullEmotionDetector()

    def _preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        if self._channels == 1:
            image = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        else:
            image = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(image, (self._input_w, self._input_h), interpolation=cv2.INTER_AREA)
        data = resized.reshape(1, self._input_h, self._input_w, self._channels).astype(np.float32)
        if self._input_detail["dtype"] == np.float32:
            return ((data - self._mean) / self._std).astype(np.float32)
        return quantize(data, self._input_detail)

    def detect(self, face_bgr: Optional[np.ndarray]) -> str:
        """Classify a cropped face. Never raises - falls back to Neutral."""
        if face_bgr is None or face_bgr.size == 0 or min(face_bgr.shape[:2]) < 8:
            return self.NEUTRAL
        try:
            self._interpreter.set_tensor(self._input_detail["index"], self._preprocess(face_bgr))
            self._interpreter.invoke()
            output = dequantize(
                self._interpreter.get_tensor(self._output_detail["index"]), self._output_detail
            ).reshape(-1)
        except Exception:
            logger.exception("Emotion inference failed; reporting Neutral.")
            return self.NEUTRAL

        index = int(np.argmax(output))
        total = float(np.sum(output))
        self.last_confidence = float(output[index] / total) if total > 0 else 0.0
        if index >= len(self.labels):
            return self.NEUTRAL
        return self.labels[index]
