"""TFLite object-detection model, filtered to the 'person' class."""

from __future__ import annotations

import os
from typing import Optional, Tuple

import cv2
import numpy as np
import tflite_runtime.interpreter as tflite


class PersonDetector:
    PERSON_CLASS_ID = 0

    def __init__(self, model_path: str, score_threshold: float) -> None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Person-detection model not found at '{model_path}'")
        self._interpreter = tflite.Interpreter(model_path=model_path)
        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()
        self._input_h = self._input_details[0]["shape"][1]
        self._input_w = self._input_details[0]["shape"][2]
        self._score_threshold = score_threshold

    def detect_best(self, frame_rgb: np.ndarray) -> Optional[Tuple[float, Tuple[int, int, int, int]]]:
        """Return (score, (xmin, ymin, xmax, ymax)) in pixel coordinates for
        the best-scoring person in the frame, or None if nothing scored
        above the configured threshold."""
        resized = cv2.resize(frame_rgb, (self._input_w, self._input_h))
        input_data = np.expand_dims(resized, axis=0).astype(self._input_details[0]["dtype"])

        self._interpreter.set_tensor(self._input_details[0]["index"], input_data)
        self._interpreter.invoke()

        boxes = self._interpreter.get_tensor(self._output_details[0]["index"])[0]
        classes = self._interpreter.get_tensor(self._output_details[1]["index"])[0]
        scores = self._interpreter.get_tensor(self._output_details[2]["index"])[0]

        best_score = 0.0
        best_box = None
        for box, cls, score in zip(boxes, classes, scores):
            if int(cls) == self.PERSON_CLASS_ID and score > self._score_threshold and score > best_score:
                best_score = float(score)
                best_box = box

        if best_box is None:
            return None

        h, w = frame_rgb.shape[:2]
        ymin, xmin, ymax, xmax = best_box
        pixel_box = (int(xmin * w), int(ymin * h), int(xmax * w), int(ymax * h))
        return best_score, pixel_box
