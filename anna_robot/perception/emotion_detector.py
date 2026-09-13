"""TFLite facial-emotion-recognition model.

Fix vs. the original prototype: this expects a *cropped face* image (as
produced by face_recognition's bounding boxes) rather than the full camera
frame, which significantly improves accuracy.
"""

from __future__ import annotations

import os

import cv2
import numpy as np
import tflite_runtime.interpreter as tflite


class EmotionDetector:
    LABELS = ["Angry", "Disgust", "Fear", "Happy", "Neutral", "Sad", "Surprise"]

    def __init__(self, model_path: str) -> None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Emotion model not found at '{model_path}'")
        self._interpreter = tflite.Interpreter(model_path=model_path)
        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()
        shape = self._input_details[0]["shape"]
        self._input_h, self._input_w = int(shape[1]), int(shape[2])

    def detect(self, face_bgr: np.ndarray) -> str:
        if face_bgr.size == 0:
            return "Neutral"
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (self._input_w, self._input_h))
        input_data = resized.reshape(1, self._input_h, self._input_w, 1).astype(np.float32) / 255.0
        self._interpreter.set_tensor(self._input_details[0]["index"], input_data)
        self._interpreter.invoke()
        output = self._interpreter.get_tensor(self._output_details[0]["index"])
        return self.LABELS[int(np.argmax(output))]
