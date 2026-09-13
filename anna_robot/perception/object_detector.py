"""Multi-class object detection on a single TFLite SSD model.

One interpreter serves every detection need: the person ANNA follows and
the furniture that describes the room around her. Running one model instead
of several is what keeps the frame budget small on a Pi.

Three robustness problems with the original single-class implementation are
fixed here, and they are the difference between "detects nothing" and
"works" on a model you did not export yourself:

* **Output order is not fixed.** Different exports emit boxes / classes /
  scores / count in different tensor orders. They are identified by shape
  and dtype instead of by index.
* **Quantised models need their scale applied.** uint8/int8 tensors are
  quantised on the way in and dequantised on the way out.
* **Boxes can fall outside the frame.** Every box is clipped to the image
  and degenerate boxes are dropped, so no downstream crop is ever empty.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..utils import box_area, box_center
from .labels import DEFAULT_CLASSES_OF_INTEREST, PERSON_LABEL, load_label_map, resolve_class_ids
from .tflite_backend import dequantize, input_scaling, load_interpreter_factory, quantize

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Detection:
    """One detected object, in pixel coordinates."""

    label: str
    score: float
    box: Tuple[int, int, int, int]  # (xmin, ymin, xmax, ymax)
    class_id: int = -1

    @property
    def center(self) -> Tuple[float, float]:
        return box_center(self.box)

    @property
    def area(self) -> float:
        return box_area(self.box)

    @property
    def is_person(self) -> bool:
        return self.label == PERSON_LABEL

    def as_dict(self) -> Dict[str, object]:
        return {"label": self.label, "score": round(self.score, 3), "box": list(self.box)}


class ObjectDetector:
    """A TFLite SSD detector filtered to a configured set of classes."""

    def __init__(
        self,
        model_path: str,
        score_threshold: float = 0.5,
        classes_of_interest: Sequence[str] = DEFAULT_CLASSES_OF_INTEREST,
        label_path: Optional[str] = None,
        max_detections: int = 10,
        num_threads: int = 2,
        iou_threshold: float = 0.55,
    ) -> None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Detection model not found at '{model_path}'. See models/README.md for where to get one."
            )
        self.model_path = model_path
        self.score_threshold = float(score_threshold)
        self.max_detections = int(max_detections)
        self.iou_threshold = float(iou_threshold)

        interpreter_factory = load_interpreter_factory()
        try:
            self._interpreter = interpreter_factory(model_path=model_path, num_threads=max(int(num_threads), 1))
        except TypeError:
            # Older runtimes have no num_threads parameter.
            self._interpreter = interpreter_factory(model_path=model_path)
        self._interpreter.allocate_tensors()

        self._input_detail = self._interpreter.get_input_details()[0]
        self._output_details = self._interpreter.get_output_details()
        _, self._input_h, self._input_w = self._input_detail["shape"][:3]
        self._input_mean, self._input_std = input_scaling(self._input_detail)
        self._tensor_roles = self._identify_outputs(self._output_details)

        self.labels = load_label_map(label_path)
        self.classes_of_interest = resolve_class_ids(self.labels, classes_of_interest)
        self.last_inference_ms = 0.0

        logger.info(
            "Object detector ready: %dx%d input, watching for %s.",
            self._input_w, self._input_h,
            ", ".join(sorted(self.classes_of_interest.values())) or "(nothing)",
        )

    # -- model introspection ---------------------------------------------
    @staticmethod
    def _identify_outputs(details: List[dict]) -> Dict[str, int]:
        """Work out which output tensor is which, by shape rather than index.

        SSD exports agree on the shapes even when they disagree on the
        order: boxes are ``[1, N, 4]``, count is ``[1]``, and of the two
        remaining ``[1, N]`` tensors the scores are the one bounded to
        ``[0, 1]`` - class ids are not.
        """
        roles: Dict[str, int] = {}
        rank2: List[int] = []
        for index, detail in enumerate(details):
            shape = list(detail["shape"])
            if len(shape) == 3 and shape[-1] == 4:
                roles["boxes"] = index
            elif len(shape) == 1 or (len(shape) == 2 and shape[-1] == 1):
                roles["count"] = index
            elif len(shape) == 2:
                rank2.append(index)

        if len(rank2) == 2:
            first, second = rank2
            # Names are the most reliable hint when the export provides them.
            names = [str(details[i].get("name", "")).lower() for i in (first, second)]
            if "score" in names[0] or "class" in names[1]:
                roles["scores"], roles["classes"] = first, second
            elif "score" in names[1] or "class" in names[0]:
                roles["scores"], roles["classes"] = second, first
            else:
                roles["scores"], roles["classes"] = first, second
        elif len(rank2) == 1:
            roles["scores"] = rank2[0]

        if "boxes" not in roles or "scores" not in roles:
            raise ValueError(
                f"Unrecognised detection model output layout: "
                f"{[list(d['shape']) for d in details]}. A standard SSD TFLite export is expected."
            )
        return roles

    def _tensor(self, role: str) -> Optional[np.ndarray]:
        index = self._tensor_roles.get(role)
        if index is None:
            return None
        detail = self._output_details[index]
        return dequantize(self._interpreter.get_tensor(detail["index"]), detail)

    # -- inference --------------------------------------------------------
    def _preprocess(self, frame_rgb: np.ndarray) -> np.ndarray:
        resized = cv2.resize(
            frame_rgb, (self._input_w, self._input_h), interpolation=cv2.INTER_LINEAR
        )
        data = np.expand_dims(resized, axis=0).astype(np.float32)
        if self._input_detail["dtype"] == np.float32:
            data = (data - self._input_mean) / self._input_std
            return data.astype(np.float32)
        return quantize(data, self._input_detail)

    def detect(self, frame_rgb: np.ndarray) -> List[Detection]:
        """Run the model and return the detections of interest, best first."""
        if frame_rgb is None or frame_rgb.size == 0:
            return []

        started = time.monotonic()
        self._interpreter.set_tensor(self._input_detail["index"], self._preprocess(frame_rgb))
        self._interpreter.invoke()
        self.last_inference_ms = (time.monotonic() - started) * 1000.0

        boxes = self._tensor("boxes")
        scores = self._tensor("scores")
        classes = self._tensor("classes")
        if boxes is None or scores is None:
            return []

        boxes = boxes[0]
        scores = scores[0]
        class_ids = (
            np.zeros(len(scores), dtype=np.int32) if classes is None else classes[0].astype(np.int32)
        )

        count_tensor = self._tensor("count")
        usable = len(scores)
        if count_tensor is not None and count_tensor.size:
            usable = min(usable, int(count_tensor.reshape(-1)[0]))

        height, width = frame_rgb.shape[:2]
        detections: List[Detection] = []
        for index in range(usable):
            score = float(scores[index])
            if score < self.score_threshold:
                continue
            class_id = int(class_ids[index])
            label = self.classes_of_interest.get(class_id)
            if label is None:
                continue
            box = self._to_pixels(boxes[index], width, height)
            if box is None:
                continue
            detections.append(Detection(label=label, score=score, box=box, class_id=class_id))

        detections.sort(key=lambda detection: detection.score, reverse=True)
        detections = self._suppress_overlaps(detections)
        return detections[: self.max_detections]

    @staticmethod
    def _to_pixels(
        box: Sequence[float], width: int, height: int
    ) -> Optional[Tuple[int, int, int, int]]:
        """Convert a normalised ``[ymin, xmin, ymax, xmax]`` box to pixels.

        The box is clipped to the frame, so a person half out of shot still
        yields a crop that downstream code can safely index.
        """
        ymin, xmin, ymax, xmax = (float(value) for value in box[:4])
        x1 = int(round(max(xmin, 0.0) * width))
        y1 = int(round(max(ymin, 0.0) * height))
        x2 = int(round(min(xmax, 1.0) * width))
        y2 = int(round(min(ymax, 1.0) * height))
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None
        return x1, y1, x2, y2

    def _suppress_overlaps(self, detections: List[Detection]) -> List[Detection]:
        """Drop duplicate boxes of the same class (per-class NMS)."""
        from ..utils import box_iou  # local import keeps the hot path tidy

        kept: List[Detection] = []
        for detection in detections:
            if any(
                other.label == detection.label and box_iou(other.box, detection.box) > self.iou_threshold
                for other in kept
            ):
                continue
            kept.append(detection)
        return kept

    # -- convenience ------------------------------------------------------
    def detect_people(self, frame_rgb: np.ndarray) -> List[Detection]:
        return [detection for detection in self.detect(frame_rgb) if detection.is_person]

    @staticmethod
    def best_person(detections: Sequence[Detection]) -> Optional[Detection]:
        """The person most likely to be the one ANNA should engage with.

        Nearest-and-most-confident: the apparent area stands in for
        proximity, which is what picks the person walking up to ANNA over
        someone crossing the far end of the corridor.
        """
        people = [detection for detection in detections if detection.is_person]
        if not people:
            return None
        return max(people, key=lambda detection: detection.area * (0.5 + detection.score))
