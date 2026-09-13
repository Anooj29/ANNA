"""Loads a directory of reference faces and matches new faces against them."""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import cv2
import face_recognition
import numpy as np

logger = logging.getLogger(__name__)


class FaceIdentifier:
    def __init__(self, known_faces_dir: str, match_threshold: float) -> None:
        self._match_threshold = match_threshold
        self._encodings: List[np.ndarray] = []
        self._names: List[str] = []
        self._load(known_faces_dir)

    def _load(self, known_faces_dir: str) -> None:
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
                    image = face_recognition.load_image_file(image_path)
                    encodings = face_recognition.face_encodings(image)
                except Exception:
                    logger.exception("Skipping unreadable reference image '%s'.", image_path)
                    continue
                if encodings:
                    self._encodings.append(encodings[0])
                    self._names.append(person)

        logger.info(
            "Loaded %d reference face(s) for %d known patient(s): %s",
            len(self._encodings),
            len(set(self._names)),
            sorted(set(self._names)),
        )

    def locate_and_encode(self, frame_bgr: np.ndarray) -> Tuple[List[Tuple[int, int, int, int]], List[np.ndarray]]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, locations)
        return locations, encodings

    def match(self, encoding: np.ndarray) -> Tuple[Optional[str], float]:
        """Return (name, distance) for the closest known face, or
        (None, inf) if there are no registered faces at all, or
        (None, distance) if the closest match isn't close enough."""
        if not self._encodings:
            return None, float("inf")
        distances = face_recognition.face_distance(self._encodings, encoding)
        best_index = int(np.argmin(distances))
        best_distance = float(distances[best_index])
        if best_distance < self._match_threshold:
            return self._names[best_index], best_distance
        return None, best_distance

    @property
    def has_known_faces(self) -> bool:
        return bool(self._encodings)
