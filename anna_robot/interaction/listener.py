"""Optional on-board microphone listening, merged with the companion link.

ANNA's original build received all speech as text from the companion app
over TCP. That still works and remains the default. This module adds a
*second, optional* source: a microphone on the Pi itself, recognised in a
background thread and pushed onto the same queue, so the robot answers to
"Hey ANNA" whether the phrase arrives from the phone app or from the room.

Everything degrades gracefully. If ``SpeechRecognition`` or PyAudio is not
installed, or no microphone is present, the listener logs why once and stays
inert - the companion link carries on unaffected.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)


class MicrophoneListener:
    """Background speech-to-text from a local microphone.

    Set ``ROBOT_MIC_ENABLED=true`` to switch it on, and install the extras:
    ``pip install SpeechRecognition PyAudio`` (plus ``sudo apt install
    portaudio19-dev`` on a Pi).
    """

    def __init__(
        self,
        enabled: bool = False,
        device_index: Optional[int] = None,
        energy_threshold: int = 300,
        pause_threshold: float = 0.6,
        phrase_time_limit: float = 6.0,
        language: str = "en-US",
        max_queue: int = 16,
    ) -> None:
        self.enabled = bool(enabled)
        self.language = language
        self.phrase_time_limit = float(phrase_time_limit)
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._recognizer = None
        self._microphone = None
        self.last_error: Optional[str] = None

        if not self.enabled:
            return
        try:
            import speech_recognition as sr  # type: ignore[import-not-found]

            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = int(energy_threshold)
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = float(pause_threshold)
            self._microphone = sr.Microphone(device_index=device_index)
            self._sr = sr
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(
                "Microphone listening is unavailable (%s). ANNA will still hear commands "
                "forwarded by the companion app. Install with: pip install SpeechRecognition PyAudio",
                exc,
            )
            self.enabled = False
            return

        self._thread = threading.Thread(target=self._run, name="microphone", daemon=True)
        self._thread.start()
        logger.info("Microphone listening is active.")

    def _run(self) -> None:  # pragma: no cover - needs real audio hardware
        try:
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
        except Exception:
            logger.exception("Could not calibrate the microphone; listening is off.")
            self.enabled = False
            return

        while not self._stop.is_set():
            try:
                with self._microphone as source:
                    audio = self._recognizer.listen(
                        source, timeout=2.0, phrase_time_limit=self.phrase_time_limit
                    )
            except Exception:
                # A listen timeout is the normal "nobody spoke" case.
                continue
            try:
                text = self._recognizer.recognize_google(audio, language=self.language)
            except self._sr.UnknownValueError:
                continue
            except Exception as exc:
                self.last_error = str(exc)
                logger.debug("Speech recognition failed: %s", exc)
                continue
            self._push(text)

    def _push(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            logger.debug("Microphone queue is full; dropping %r.", text)

    def inject(self, text: str) -> None:
        """Feed text in as though it had been heard (tests, dashboards)."""
        self._push(text)

    def drain(self) -> List[str]:
        """Return everything heard since the last call. Never blocks."""
        heard: List[str] = []
        while True:
            try:
                heard.append(self._queue.get_nowait())
            except queue.Empty:
                return heard

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
