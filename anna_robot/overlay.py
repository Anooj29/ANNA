"""Draws ANNA's perception onto the frame shown to staff.

The annotated frame goes to both the local debug window and the clinician
vision dashboard, so what is drawn here is what staff use to judge whether
the robot is seeing what they think it is. It is drawing only - nothing in
this module influences behaviour.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import cv2
import numpy as np

from .control.follower import DriveCommand
from .control.visual import VisualTarget
from .head_tracker import HeadTracker
from .perception.object_detector import Detection

FONT = cv2.FONT_HERSHEY_SIMPLEX

#: BGR. Person green, other objects blue-grey, faces amber - matching the
#: colour key the vision dashboard documents.
PERSON_COLOR = (0, 255, 0)
OBJECT_COLOR = (200, 160, 60)
FACE_COLOR = (0, 191, 255)
TARGET_COLOR = (0, 215, 255)
TEXT_COLOR = (255, 255, 255)
PANEL_COLOR = (32, 32, 32)
WARN_COLOR = (0, 128, 255)


def _label(frame: np.ndarray, text: str, x: int, y: int, color: Tuple[int, int, int]) -> None:
    """Draw text with a filled backing box so it stays readable on any scene."""
    (width, height), baseline = cv2.getTextSize(text, FONT, 0.5, 1)
    y = max(y, height + 4)
    cv2.rectangle(frame, (x, y - height - baseline - 2), (x + width + 6, y + 2), PANEL_COLOR, -1)
    cv2.putText(frame, text, (x + 3, y - baseline + 1), FONT, 0.5, color, 1, cv2.LINE_AA)


def draw_detections(frame: np.ndarray, detections: Sequence[Detection]) -> None:
    for detection in detections:
        xmin, ymin, xmax, ymax = detection.box
        color = PERSON_COLOR if detection.is_person else OBJECT_COLOR
        cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), color, 2)
        _label(frame, f"{detection.label} {detection.score:.2f}", xmin, ymin - 4, color)


def draw_faces(
    frame: np.ndarray,
    locations: Sequence[Tuple[int, int, int, int]],
    caption: Optional[str] = None,
) -> None:
    for index, (top, right, bottom, left) in enumerate(locations):
        cv2.rectangle(frame, (left, top), (right, bottom), FACE_COLOR, 2)
        _label(frame, "Face", left, top - 4, FACE_COLOR)
        if caption and index == 0:
            _label(frame, caption, left, min(bottom + 20, frame.shape[0] - 4), FACE_COLOR)


def draw_target(frame: np.ndarray, target: Optional[VisualTarget]) -> None:
    """Mark the tracked person and the frame centre the robot steers to."""
    height, width = frame.shape[:2]
    center_x = width // 2
    cv2.line(frame, (center_x, 0), (center_x, height), (70, 70, 70), 1)
    if target is None:
        return
    x, y = int(target.center_px[0]), int(target.center_px[1])
    cv2.circle(frame, (x, y), 7, TARGET_COLOR, 2)
    cv2.line(frame, (center_x, y), (x, y), TARGET_COLOR, 1)
    distance = "?" if target.distance_cm is None else f"{target.distance_cm:.0f}cm"
    _label(frame, f"target {distance} bearing {target.bearing:+.2f}", x + 10, y, TARGET_COLOR)


def draw_head(frame: np.ndarray, head: HeadTracker) -> None:
    """Show head angles, and warn clearly when an axis is against its stop."""
    if not head.enabled:
        return
    pan, tilt = head.angles
    color = WARN_COLOR if head.at_limit else TEXT_COLOR
    text = f"head pan {pan:+.0f} tilt {tilt:+.0f}" + (" [LIMIT]" if head.at_limit else "")
    _label(frame, text, 8, frame.shape[0] - 10, color)


def draw_status(
    frame: np.ndarray,
    state: str,
    fps: float,
    distance_cm: float,
    extras: Optional[Dict[str, str]] = None,
) -> None:
    lines = [f"{state}  {fps:4.1f} FPS  {distance_cm:5.1f}cm"]
    if extras:
        lines.extend(f"{key}: {value}" for key, value in extras.items())
    for index, line in enumerate(lines):
        _label(frame, line, 8, 22 + index * 20, TEXT_COLOR)


def draw_drive(frame: np.ndarray, command: DriveCommand) -> None:
    """A small bar showing the commanded linear/angular velocity."""
    height, width = frame.shape[:2]
    origin_x, origin_y = width - 90, height - 40
    cv2.rectangle(frame, (origin_x - 10, origin_y - 30), (width - 8, origin_y + 18), PANEL_COLOR, -1)
    cv2.line(frame, (origin_x + 35, origin_y), (origin_x + 35, origin_y - 25), (90, 90, 90), 1)
    cv2.line(
        frame, (origin_x + 35, origin_y),
        (origin_x + 35 - int(command.angular * 35), origin_y - int(command.linear * 25)),
        PERSON_COLOR if command.linear or command.angular else (90, 90, 90), 2,
    )
    _label(frame, command.state.value, origin_x - 8, origin_y + 16, TEXT_COLOR)
