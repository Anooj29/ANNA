"""Loads a directory of reference faces and matches new faces against them.

Face recognition is by far the most expensive thing ANNA does per frame, so
this module is built to do less of it:

* Detection runs on a **downscaled** copy of the frame (``detection_scale``).
  Locations are scaled back up, so callers still get full-resolution boxes.
* Encoding - the really costly half - runs only on the faces that matter.
* ``face_recognition`` is imported lazily, so the rest of the robot (and the
  test suite) works on a machine where dlib is not installed.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

#: (top, right, bottom, left), matching the face_recognition convention.
FaceLocation = Tuple[int, int, int, int]

_face_recognition = None
_import_error: Optional[BaseException] = None


def _library():
    """Import ``face_recognition`` on first use, and only once."""
    global _face_recognition, _import_error
    if _face_recognition is None and _import_error is None:
        try:
            import face_recognition  # type: ignore[import-not-found]

            _face_recognition = face_recognition
        except Exception as exc:  # pragma: no cover - depends on the machine
            _import_error = exc
            logger.error(
                "face_recognition/dlib is unavailable (%s). Patient recognition is disabled; "
                "everything else keeps working.", exc,
            )
    return _face_recognition


class FaceIdentifier:
    def __init__(
        self,
        known_faces_dir: str,
        match_threshold: float,
        detection_scale: float = 0.5,
        model: str = "hog",
        upsample: int = 1,
    ) -> None:
        self._match_threshold = float(match_threshold)
        self._detection_scale = float(np.clip(detection_scale, 0.1, 1.0))
        self._model = model
        self._upsample = max(int(upsample), 0)
        self._encodings: List[np.ndarray] = []
        self._names: List[str] = []
        self.known_faces_dir = known_faces_dir
        self._load(known_faces_dir)

    # -- reference faces --------------------------------------------------
    def _load(self, known_faces_dir: str) -> None:
        library = _library()
        if library is None:
            return
        if not os.path.isdir(known_faces_dir):
            logger.warning(
                "Known-faces directory '%s' does not exist; creating it. No patients are registered yet.",
                known_faces_dir,
            )
            os.makedirs(known_faces_dir, exist_ok=True)
            return

        for person in sorted(os.listdir(known_faces_dir)):
            person_dir = os.path.join(known_faces_dir, person)
            if not os.path.isdir(person_dir):
                continue
            for image_name in sorted(os.listdir(person_dir)):
                image_path = os.path.join(person_dir, image_name)
                try:
                    image = library.load_image_file(image_path)
                    encodings = library.face_encodings(image)
                except Exception:
                    logger.exception("Skipping unreadable reference image '%s'.", image_path)
                    continue
                if encodings:
                    self._encodings.append(encodings[0])
                    self._names.append(person)
                else:
                    logger.warning("No face found in reference image '%s'; skipping it.", image_path)

        logger.info(
            "Loaded %d reference face(s) for %d known patient(s): %s",
            len(self._encodings), len(set(self._names)), sorted(set(self._names)),
        )

    def reload(self) -> int:
        """Re-read the reference directory (after reception registers someone)."""
        self._encodings.clear()
        self._names.clear()
        self._load(self.known_faces_dir)
        return len(self._encodings)

    # -- per-frame work ---------------------------------------------------
    def locate(self, frame_bgr: np.ndarray) -> List[FaceLocation]:
        """Find faces, working on a downscaled frame for speed."""
        library = _library()
        if library is None or frame_bgr is None or frame_bgr.size == 0:
            return []
        scale = self._detection_scale
        small = (
            frame_bgr if scale >= 0.999
            else cv2.resize(frame_bgr, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        )
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        try:
            locations = library.face_locations(rgb, number_of_times_to_upsample=self._upsample, model=self._model)
        except Exception:
            logger.exception("Face detection failed for this frame.")
            return []
        if scale >= 0.999:
            return list(locations)
        inverse = 1.0 / scale
        height, width = frame_bgr.shape[:2]
        return [
            (
                int(min(top * inverse, height)),
                int(min(right * inverse, width)),
                int(min(bottom * inverse, height)),
                int(min(left * inverse, width)),
            )
            for top, right, bottom, left in locations
        ]

    def encode(
        self, frame_bgr: np.ndarray, locations: List[FaceLocation], limit: int = 1
    ) -> List[np.ndarray]:
        """Encode at most ``limit`` faces - encoding is the expensive half."""
        library = _library()
        if library is None or not locations:
            return []
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        try:
            return list(library.face_encodings(rgb, locations[:limit]))
        except Exception:
            logger.exception("Face encoding failed for this frame.")
            return []

    def locate_and_encode(
        self, frame_bgr: np.ndarray, limit: int = 1
    ) -> Tuple[List[FaceLocation], List[np.ndarray]]:
        """Locate faces and encode the first ``limit`` of them."""
        locations = self.locate(frame_bgr)
        return locations, self.encode(frame_bgr, locations, limit=limit)

    def match(self, encoding: np.ndarray) -> Tuple[Optional[str], float]:
        """Return ``(name, distance)`` for the closest known face, or
        ``(None, inf)`` when nothing is registered, or ``(None, distance)``
        when the closest match is not close enough."""
        library = _library()
        if library is None or not self._encodings:
            return None, float("inf")
        distances = library.face_distance(self._encodings, encoding)
        best_index = int(np.argmin(distances))
        best_distance = float(distances[best_index])
        if best_distance < self._match_threshold:
            return self._names[best_index], best_distance
        return None, best_distance

    @staticmethod
    def crop(frame_bgr: np.ndarray, location: FaceLocation, margin: float = 0.0) -> np.ndarray:
        """Safely crop a face, clipped to the frame (never returns an
        out-of-bounds or inverted slice)."""
        height, width = frame_bgr.shape[:2]
        top, right, bottom, left = location
        if margin > 0:
            pad_y = int((bottom - top) * margin)
            pad_x = int((right - left) * margin)
            top, bottom, left, right = top - pad_y, bottom + pad_y, left - pad_x, right + pad_x
        top = int(np.clip(top, 0, height))
        bottom = int(np.clip(bottom, 0, height))
        left = int(np.clip(left, 0, width))
        right = int(np.clip(right, 0, width))
        if bottom <= top or right <= left:
            return np.empty((0, 0, 3), dtype=frame_bgr.dtype)
        return frame_bgr[top:bottom, left:right]

    @property
    def has_known_faces(self) -> bool:
        return bool(self._encodings)

    @property
    def known_names(self) -> List[str]:
        return sorted(set(self._names))

    @property
    def available(self) -> bool:
        """False when dlib/face_recognition could not be imported."""
        return _library() is not None
