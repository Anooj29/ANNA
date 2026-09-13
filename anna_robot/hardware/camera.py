"""Threaded camera capture that always hands back the newest frame.

A plain ``VideoCapture.read()`` in the control loop returns the *oldest*
buffered frame, so every slow iteration adds permanent latency between what
the camera sees and what the robot reacts to. This grabber drains the driver
buffer in its own thread and keeps only the latest frame, which is the
single biggest win for "the robot reacts late" lag. It also reopens the
device by itself if the camera drops off the USB bus.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

from ..utils import ExponentialFilter

logger = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Raised when no camera in the configured index list can be opened."""


class ThreadedCamera:
    def __init__(
        self,
        indices: Sequence[int] = (0, 1),
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        use_mjpg: bool = True,
        buffer_size: int = 1,
        reopen_after_failures: int = 60,
    ) -> None:
        self._indices = tuple(indices) or (0,)
        self._width = int(width)
        self._height = int(height)
        self._fps = int(fps)
        self._use_mjpg = bool(use_mjpg)
        self._buffer_size = max(int(buffer_size), 1)
        self._reopen_after_failures = max(int(reopen_after_failures), 1)

        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._frame_id = 0
        self._captured_at = 0.0
        self._new_frame = threading.Event()
        self._stop = threading.Event()
        self._rate = ExponentialFilter(1.0)

        self._capture, self.index = self._open_any()
        self._thread = threading.Thread(target=self._run, name="camera-capture", daemon=True)
        self._thread.start()

    # -- opening ----------------------------------------------------------
    def _configure(self, capture: "cv2.VideoCapture") -> None:
        """Apply the properties that actually matter for latency and speed.

        MJPG matters on USB cameras: the default YUYV mode saturates USB 2.0
        bandwidth at 640x480 and silently drops the frame rate. A buffer size
        of 1 keeps the driver from queueing stale frames behind us.
        """
        if self._use_mjpg:
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        capture.set(cv2.CAP_PROP_FPS, self._fps)
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, self._buffer_size)
        except Exception:  # pragma: no cover - some backends reject this
            logger.debug("Camera backend does not support CAP_PROP_BUFFERSIZE.")

    def _open_index(self, index: int) -> Optional["cv2.VideoCapture"]:
        # CAP_V4L2 first (the Pi's native path), then the platform default so
        # the same code still opens a camera on a laptop.
        for api in (getattr(cv2, "CAP_V4L2", cv2.CAP_ANY), cv2.CAP_ANY):
            capture = cv2.VideoCapture(index, api)
            if capture.isOpened():
                self._configure(capture)
                ok, _ = capture.read()
                if ok:
                    return capture
            capture.release()
        return None

    def _open_any(self) -> Tuple["cv2.VideoCapture", int]:
        for index in self._indices:
            capture = self._open_index(index)
            if capture is not None:
                actual = (
                    int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                )
                logger.info("Camera opened at index %d (%dx%d).", index, *actual)
                return capture, index
            logger.warning("Camera index %d failed to open, trying next...", index)
        raise CameraError(f"Could not open any camera. Checked indices: {self._indices}")

    # -- capture thread ---------------------------------------------------
    def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            ok, frame = self._capture.read()
            if not ok or frame is None:
                failures += 1
                if failures % 10 == 1:
                    logger.warning("Camera frame read failed (%d in a row).", failures)
                if failures >= self._reopen_after_failures:
                    self._reopen()
                    failures = 0
                time.sleep(0.02)
                continue

            failures = 0
            now = time.monotonic()
            with self._lock:
                if self._captured_at:
                    self._rate.update(now - self._captured_at, now - self._captured_at)
                self._frame = frame
                self._frame_id += 1
                self._captured_at = now
            self._new_frame.set()

    def _reopen(self) -> None:
        logger.warning("Reopening the camera after repeated read failures...")
        try:
            self._capture.release()
        except Exception:
            logger.debug("Camera release failed during reopen.", exc_info=True)
        while not self._stop.is_set():
            try:
                self._capture, self.index = self._open_any()
                logger.info("Camera recovered on index %d.", self.index)
                return
            except CameraError:
                logger.error("Camera still unavailable; retrying in 2s.")
                self._stop.wait(2.0)

    # -- consumer API -----------------------------------------------------
    def read(self, timeout: Optional[float] = 1.0) -> Optional[np.ndarray]:
        """Return the most recent frame, waiting up to ``timeout`` for one.

        The frame is copied so callers can annotate it without racing the
        capture thread.
        """
        if not self._new_frame.wait(timeout if timeout is not None else 0.0):
            with self._lock:
                return None if self._frame is None else self._frame.copy()
        with self._lock:
            self._new_frame.clear()
            return None if self._frame is None else self._frame.copy()

    @property
    def frame_id(self) -> int:
        with self._lock:
            return self._frame_id

    @property
    def fps(self) -> float:
        period = self._rate.value
        return 1.0 / period if period else 0.0

    @property
    def age_s(self) -> float:
        """Seconds since the newest frame was captured (staleness watchdog)."""
        with self._lock:
            return 0.0 if not self._captured_at else time.monotonic() - self._captured_at

    def release(self) -> None:
        self._stop.set()
        self._new_frame.set()
        self._thread.join(timeout=2.0)
        try:
            self._capture.release()
        except Exception:
            logger.debug("Camera release failed.", exc_info=True)

    def __enter__(self) -> "ThreadedCamera":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
