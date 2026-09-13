"""Newline-framed JSON telemetry link to a companion laptop/dashboard.

Rewritten to fix three faults in the original link that only show up once
it is actually used for a while:

* **No message framing.** ``recv`` was treated as one command per call, so
  two commands arriving in the same TCP segment became one corrupt string
  ("yes buddycheck pulse") and a command split across segments was lost.
  Input is now buffered and split on newlines.
* **No disconnect detection.** A closed peer returns an empty read forever,
  which looked exactly like "no command", so the link died silently and
  never recovered. Disconnects are now detected and a new client is accepted
  in the background.
* **A blocking accept in the constructor.** Startup hung until a companion
  connected, with no way to run the robot standalone. Waiting is now
  optional (``wait_for_client``).
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_LINE_BYTES = 64 * 1024


class TelemetryLink:
    """Streams status packets out and reads command lines back.

    One client at a time, exactly as before; when it goes away the listener
    keeps running and the next one is accepted automatically.
    """

    def __init__(
        self,
        port: int,
        host: str = "",
        wait_for_client: bool = True,
        connect_timeout_s: Optional[float] = None,
    ) -> None:
        self.port = int(port)
        self._lock = threading.Lock()
        self._conn: Optional[socket.socket] = None
        self._peer: Optional[str] = None
        self._buffer = b""
        self._peer_uses_newlines = False
        self._closed = threading.Event()
        self._connected = threading.Event()

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind((host, self.port))
            self._server.listen(1)
        except OSError:
            # Do not leak the bound socket if startup fails.
            self._server.close()
            raise
        logger.info("Telemetry listening on port %s...", self.port)

        self._acceptor = threading.Thread(target=self._accept_loop, name="telemetry-accept", daemon=True)
        self._acceptor.start()
        if wait_for_client:
            logger.info("Waiting for a companion connection on port %s...", self.port)
            if not self._connected.wait(connect_timeout_s):
                logger.warning(
                    "No companion connected within %.0fs; continuing without one. "
                    "It can still connect at any time.", connect_timeout_s or 0.0,
                )

    # -- connection handling ---------------------------------------------
    def _accept_loop(self) -> None:
        self._server.settimeout(0.5)
        while not self._closed.is_set():
            try:
                conn, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                if not self._closed.is_set():
                    logger.debug("Telemetry accept failed.", exc_info=True)
                return
            conn.setblocking(False)
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            with self._lock:
                previous = self._conn
                self._conn = conn
                self._peer = f"{addr[0]}:{addr[1]}"
                self._buffer = b""
                self._peer_uses_newlines = False
            if previous is not None:
                logger.info("Replacing the previous companion connection.")
                _close_quietly(previous)
            self._connected.set()
            logger.info("Companion connected: %s", self._peer)

    def _drop(self, reason: str) -> None:
        with self._lock:
            conn, self._conn, self._buffer = self._conn, None, b""
            peer, self._peer = self._peer, None
        if conn is not None:
            _close_quietly(conn)
            self._connected.clear()
            logger.info("Companion %s disconnected (%s); waiting for a new connection.", peer, reason)

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._conn is not None

    @property
    def peer(self) -> Optional[str]:
        with self._lock:
            return self._peer

    # -- sending ----------------------------------------------------------
    def send(self, payload: Dict[str, object]) -> bool:
        """Send one JSON packet. Returns False when nobody is listening."""
        with self._lock:
            conn = self._conn
        if conn is None:
            return False
        try:
            data = (json.dumps(payload, default=str) + "\n").encode("utf-8")
        except (TypeError, ValueError):
            logger.exception("Telemetry payload could not be serialised; dropping it.")
            return False
        try:
            conn.sendall(data)
            return True
        except BlockingIOError:
            # The companion is not reading fast enough; skipping one packet is
            # the right call - the next one carries the same live state.
            logger.debug("Telemetry send would block; dropping this packet.")
            return False
        except OSError as exc:
            self._drop(str(exc))
            return False

    # -- receiving --------------------------------------------------------
    def receive_commands(self) -> List[str]:
        """Return every complete command line received since the last call."""
        with self._lock:
            conn = self._conn
        if conn is None:
            return []

        while True:
            try:
                chunk = conn.recv(4096)
            except BlockingIOError:
                break
            except OSError as exc:
                self._drop(str(exc))
                return []
            if not chunk:  # An empty read means the peer closed the socket.
                self._drop("peer closed the connection")
                return []
            with self._lock:
                self._buffer += chunk
                if len(self._buffer) > MAX_LINE_BYTES:
                    logger.warning("Telemetry input exceeded %d bytes without a newline; discarding it.",
                                   MAX_LINE_BYTES)
                    self._buffer = b""

        with self._lock:
            if b"\n" in self._buffer:
                # This companion frames its messages, so trust the framing:
                # anything after the last newline is an incomplete command
                # and stays buffered until the rest of it arrives.
                self._peer_uses_newlines = True
                raw, _, self._buffer = self._buffer.rpartition(b"\n")
                lines = raw.split(b"\n")
            elif self._buffer and not self._peer_uses_newlines:
                # The original companion app sent bare text with no newline
                # at all, so until one is seen the whole buffer is one
                # command. That keeps existing companions working.
                lines, self._buffer = [self._buffer], b""
            else:
                return []

        commands = []
        for line in lines:
            text = line.decode("utf-8", errors="ignore").strip().lower()
            if text:
                commands.append(text)
                logger.debug("Command received: %r", text)
        return commands

    def receive_command(self) -> str:
        """The next single command, or "" - the original API, still supported."""
        commands = self.receive_commands()
        return commands[0] if commands else ""

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            conn, self._conn = self._conn, None
        if conn is not None:
            _close_quietly(conn)
        _close_quietly(self._server)
        self._acceptor.join(timeout=2.0)


def _close_quietly(sock: socket.socket) -> None:
    try:
        sock.close()
    except Exception:
        logger.debug("Socket failed to close cleanly.", exc_info=True)
