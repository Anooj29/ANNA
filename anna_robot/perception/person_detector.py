"""Person detection - the original API, now backed by the multi-class model.

Kept as a thin façade so existing callers (and the documented behaviour of
``detect_best``) keep working unchanged, while new code can reach the full
multi-class detector underneath through :attr:`PersonDetector.detector`.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

from .labels import PERSON_LABEL
from .object_detector import Detection, ObjectDetector


class PersonDetector:
    """Detects people (and, via :attr:`detector`, the other watched classes)."""

    PERSON_CLASS_ID = 0

    def __init__(
        self,
        model_path: str,
        score_threshold: float,
        classes_of_interest: Optional[Sequence[str]] = None,
        label_path: Optional[str] = None,
        num_threads: int = 2,
    ) -> None:
        self.detector = ObjectDetector(
            model_path=model_path,
            score_threshold=score_threshold,
            classes_of_interest=classes_of_interest or (PERSON_LABEL,),
            label_path=label_path,
            num_threads=num_threads,
        )

    def detect(self, frame_rgb: np.ndarray) -> List[Detection]:
        """Every watched object in the frame, best score first."""
        return self.detector.detect(frame_rgb)

    def detect_people(self, frame_rgb: np.ndarray) -> List[Detection]:
        return self.detector.detect_people(frame_rgb)

    def detect_best(
        self, frame_rgb: np.ndarray
    ) -> Optional[Tuple[float, Tuple[int, int, int, int]]]:
        """Return ``(score, (xmin, ymin, xmax, ymax))`` for the best person
        in the frame, or ``None`` if nothing scored above the threshold."""
        best = ObjectDetector.best_person(self.detector.detect(frame_rgb))
        return None if best is None else (best.score, best.box)
