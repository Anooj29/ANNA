"""Non-blocking JSON-over-TCP telemetry link to a companion laptop/dashboard."""

from __future__ import annotations

import json
import logging
import socket
from typing import Dict

logger = logging.getLogger(__name__)


class TelemetryLink:
    """Accepts exactly one client connection, then streams a status packet
    each control-loop iteration and reads back any voice-command text the
    companion app forwards."""

    def __init__(self, port: int) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("", port))
        self._server.listen(1)
        logger.info("Waiting for a companion connection on port %s...", port)
        self._conn, addr = self._server.accept()
        self._conn.setblocking(False)
        logger.info("Companion connected: %s", addr)

    def send(self, payload: Dict[str, object]) -> None:
        try:
            self._conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        except OSError:
            logger.debug("Telemetry send failed; companion may have disconnected.")

    def receive_command(self) -> str | dict:
        try:
            data = self._conn.recv(1024).decode("utf-8", errors="ignore")
        except BlockingIOError:
            return ""
        except OSError:
            logger.debug("Telemetry receive failed; companion may have disconnected.")
            return ""
        if not data:
            return ""

        raw_command = data.strip()
        logger.debug("Command received: %r", raw_command)

        try:
            # Attempt to parse as JSON for structured commands
            return json.loads(raw_command)
        except json.JSONDecodeError:
            # Fallback to plain string for legacy commands
            return raw_command.lower()

    def close(self) -> None:
        for sock in (self._conn, self._server):
            try:
                sock.close()
            except Exception:
                pass
