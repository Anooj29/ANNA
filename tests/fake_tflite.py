"""A fake TFLite interpreter, so detection can be tested without a model.

It deliberately emits its output tensors in a *shuffled* order, because
that is exactly the real-world variation that used to make the detector
silently return nothing.
"""

from __future__ import annotations

from typing import List, Sequence

import numpy as np


class FakeSsdInterpreter:
    """Mimics a TFLite SSD export with a configurable detection list."""

    #: (class_id, score, [ymin, xmin, ymax, xmax]) in normalised coordinates.
    detections: Sequence = ()
    quantised = False
    capacity = 10

    def __init__(self, model_path=None, num_threads=None):
        self.model_path = model_path
        self.invoked = 0
        self._input = None

    # -- interpreter API --------------------------------------------------
    def allocate_tensors(self) -> None:
        pass

    def get_input_details(self) -> List[dict]:
        if self.quantised:
            return [{"index": 0, "shape": np.array([1, 300, 300, 3]),
                     "dtype": np.uint8, "quantization": (0.0078125, 128)}]
        return [{"index": 0, "shape": np.array([1, 300, 300, 3]),
                 "dtype": np.float32, "quantization": (0.0, 0)}]

    def get_output_details(self) -> List[dict]:
        # Order on purpose: classes, boxes, count, scores.
        common = {"dtype": np.float32, "quantization": (0.0, 0)}
        return [
            {"index": 1, "shape": np.array([1, self.capacity]), "name": "detection_classes", **common},
            {"index": 0, "shape": np.array([1, self.capacity, 4]), "name": "detection_boxes", **common},
            {"index": 3, "shape": np.array([1]), "name": "num_detections", **common},
            {"index": 2, "shape": np.array([1, self.capacity]), "name": "detection_scores", **common},
        ]

    def set_tensor(self, index, data) -> None:
        self._input = data

    @property
    def last_input(self):
        return self._input

    def invoke(self) -> None:
        self.invoked += 1

    def get_tensor(self, index):
        boxes = np.zeros((1, self.capacity, 4), np.float32)
        classes = np.zeros((1, self.capacity), np.float32)
        scores = np.zeros((1, self.capacity), np.float32)
        for slot, (class_id, score, box) in enumerate(self.detections[: self.capacity]):
            classes[0, slot] = class_id
            scores[0, slot] = score
            boxes[0, slot] = box
        return {
            0: boxes,
            1: classes,
            2: scores,
            3: np.array([float(min(len(self.detections), self.capacity))], np.float32),
        }[index]


def make_detector(detections, **kwargs):
    """Build an ObjectDetector backed by the fake interpreter."""
    from unittest import mock

    import anna_robot.perception.object_detector as module

    interpreter = type("Configured", (FakeSsdInterpreter,), {"detections": tuple(detections)})
    with mock.patch.object(module, "load_interpreter_factory", return_value=interpreter), \
            mock.patch("os.path.exists", return_value=True):
        return module.ObjectDetector("fake-model.tflite", **kwargs)
