"""Is-there-a-face check for intake photos.

This deliberately does NOT identify who the face belongs to - that's the
robot's job later, using the real face_recognition/dlib library on the
Pi. This only answers "how many faces are in this photo?", which is all
the receptionist dashboard needs, and it does that with cascades that
ship inside opencv-python-headless already - no model file to download,
no C++ build toolchain, works offline.

A single frontal cascade (the old approach) misses anything but a
fairly straight-on face, which is exactly what was happening with
side-view photos. This combines:
  - two frontal cascades (default + alt2, they disagree occasionally)
  - the profile cascade, run once normally and once on a mirrored copy
    of the image (it's only trained on one profile direction)
and de-duplicates overlapping detections so the same real face isn't
counted twice just because two cascades both found it.
"""

from __future__ import annotations

import cv2

_FRONTAL_CASCADES = [
    cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml"),
    cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"),
]
_PROFILE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")

_DETECT_KWARGS = dict(scaleFactor=1.1, minNeighbors=6, minSize=(80, 80))


def _iou(a, b) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _dedupe(boxes: list, iou_threshold: float = 0.3) -> list:
    kept: list = []
    for box in boxes:
        if not any(_iou(box, existing) > iou_threshold for existing in kept):
            kept.append(box)
    return kept


def count_faces(image_path: str) -> int:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not decode image at {image_path}")

    gray = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))

    boxes: list = []
    for cascade in _FRONTAL_CASCADES:
        boxes.extend(cascade.detectMultiScale(gray, **_DETECT_KWARGS))

    boxes.extend(_PROFILE_CASCADE.detectMultiScale(gray, **_DETECT_KWARGS))

    # The profile cascade only recognises faces looking one way, so also
    # check a horizontally-flipped copy for the other direction, then map
    # the boxes it finds back into the original image's coordinates.
    flipped = cv2.flip(gray, 1)
    width = gray.shape[1]
    for (x, y, w, h) in _PROFILE_CASCADE.detectMultiScale(flipped, **_DETECT_KWARGS):
        boxes.append((width - x - w, y, w, h))

    return len(_dedupe(boxes))
