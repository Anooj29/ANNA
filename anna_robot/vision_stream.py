"""Small, dependency-free MJPEG server for ANNA's annotated camera frames."""

from __future__ import annotations

import logging
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class VisionStream:
    """Publishes the most recent camera frame without ever controlling ANNA.

    The robot control loop supplies frames with its detection annotations
    already drawn. Viewers can only consume ``/stream.mjpg``; no endpoint in
    this server accepts movement, camera, or robot-state commands.
    """

    def __init__(
        self,
        host: str,
        port: int,
        token: Optional[str] = None,
        jpeg_quality: int = 80,
        max_fps: float = 15.0,
        max_width: int = 640,
    ) -> None:
        self._token = token or ""
        self._jpeg_quality = int(jpeg_quality)
        self._min_period_s = 1.0 / max_fps if max_fps > 0 else 0.0
        self._max_width = int(max_width)
        self._condition = threading.Condition()
        self._jpeg: Optional[bytes] = None
        self._frame_number = 0
        self._last_encode = 0.0
        self._viewers = 0
        self._running = True
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                if parsed.path == "/healthz":
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                    return
                if parsed.path != "/stream.mjpg":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                supplied = parse_qs(parsed.query).get("token", [""])[0]
                if owner._token and supplied != owner._token:
                    self.send_error(HTTPStatus.UNAUTHORIZED)
                    return

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Connection", "close")
                self.end_headers()
                with owner._condition:
                    owner._viewers += 1
                try:
                    last_frame = -1
                    while owner._running:
                        with owner._condition:
                            owner._condition.wait_for(
                                lambda: owner._frame_number != last_frame or not owner._running, timeout=1
                            )
                            jpeg = owner._jpeg
                            last_frame = owner._frame_number
                        if jpeg is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                        self.wfile.write(jpeg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    with owner._condition:
                        owner._viewers = max(owner._viewers - 1, 0)

            def log_message(self, format: str, *args: object) -> None:
                logger.debug("Vision stream: " + format, *args)

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="vision-stream", daemon=True)
        self._thread.start()
        logger.info("Robot vision stream available at http://%s:%d/stream.mjpg", host, port)

    @property
    def viewers(self) -> int:
        """How many clients are currently watching the stream."""
        with self._condition:
            return self._viewers

    def publish(self, frame: np.ndarray) -> bool:
        """JPEG-encode an annotated BGR frame for all connected viewers.

        Encoding is skipped when nobody is watching, and rate-limited when
        somebody is. On a Pi that is real control-loop time back: the old
        code encoded every single frame even with zero viewers.
        """
        if frame is None or frame.size == 0:
            return False
        now = time.monotonic()
        with self._condition:
            if self._viewers == 0:
                return False
            if self._min_period_s and (now - self._last_encode) < self._min_period_s:
                return False
            self._last_encode = now

        if 0 < self._max_width < frame.shape[1]:
            scale = self._max_width / float(frame.shape[1])
            frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
        if not ok:
            logger.warning("Unable to encode camera frame for vision stream.")
            return False
        with self._condition:
            self._jpeg = encoded.tobytes()
            self._frame_number += 1
            self._condition.notify_all()
        return True

    def close(self) -> None:
        self._running = False
        with self._condition:
            self._condition.notify_all()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
