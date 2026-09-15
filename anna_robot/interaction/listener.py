"""Optional on-board microphone listening using offline Vosk STT.

ANNA's original build received speech as text from the companion app over
TCP. This module adds a second, optional source: a microphone on the Pi.

The microphone audio is captured with PyAudio at the rate supported by the
USB microphone, resampled to 16 kHz with SciPy, and recognised locally by
Vosk. No internet connection or Google Speech Recognition API is required.

Everything degrades gracefully. If PyAudio, Vosk, SciPy, or the microphone
is unavailable, the listener logs why once and stays inert.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import List, Optional

import numpy as np
from scipy.signal import resample_poly

logger = logging.getLogger(__name__)


class MicrophoneListener:
    """Background offline speech-to-text from a local microphone.

    Set ``ROBOT_MIC_ENABLED=true`` to switch it on.

    The USB microphone is captured at 44.1 kHz and audio is resampled to
    16 kHz before being passed to Vosk.
    """

    MIC_RATE = 44100
    VOSK_RATE = 16000
    CHANNELS = 1
    CHUNK = 4410

    def __init__(
        self,
        enabled: bool = False,
        device_index: Optional[int] = None,
        energy_threshold: int = 300,
        pause_threshold: float = 0.6,
        phrase_time_limit: float = 6.0,
        language: str = "en-US",
        max_queue: int = 16,
        model_path: str = "models/vosk-model-small-en-us-0.15",
    ) -> None:
        self.enabled = bool(enabled)
        self.language = language
        self.phrase_time_limit = float(phrase_time_limit)
        self.device_index = device_index
        self.model_path = model_path

        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._audio = None
        self._stream = None
        self._recognizer = None
        self._model = None

        self.last_error: Optional[str] = None

        if not self.enabled:
            return

        try:
            import pyaudio  # type: ignore[import-not-found]
            from vosk import KaldiRecognizer, Model  # type: ignore[import-not-found]

            self._pyaudio_module = pyaudio

            logger.info("Loading Vosk model from %s", self.model_path)
            self._model = Model(self.model_path)
            self._recognizer = KaldiRecognizer(self._model, self.VOSK_RATE)

            self._audio = pyaudio.PyAudio()

            self._stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=self.CHANNELS,
                rate=self.MIC_RATE,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=self.CHUNK,
            )

            self._stream.start_stream()

        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(
                "Microphone listening is unavailable (%s). "
                "ANNA will still hear commands forwarded by the companion app.",
                exc,
            )
            self._cleanup_audio()
            self.enabled = False
            return

        self._thread = threading.Thread(
            target=self._run,
            name="microphone",
            daemon=True,
        )
        self._thread.start()

        logger.info(
            "Offline microphone listening is active "
            "(%d Hz microphone -> %d Hz Vosk).",
            self.MIC_RATE,
            self.VOSK_RATE,
        )

    def _run(self) -> None:  # pragma: no cover - needs real audio hardware
        while not self._stop.is_set():
            try:
                data = self._stream.read(
                    self.CHUNK,
                    exception_on_overflow=False,
                )

                samples = np.frombuffer(
                    data,
                    dtype=np.int16,
                )

                resampled = resample_poly(
                    samples,
                    self.VOSK_RATE,
                    self.MIC_RATE,
                )

                resampled = np.asarray(
                    resampled,
                    dtype=np.int16,
                )

                if self._recognizer.AcceptWaveform(resampled.tobytes()):
                    result = json.loads(
                        self._recognizer.Result()
                    )
                    text = result.get("text", "")

                    if text:
                        logger.debug("Vosk recognized: %r", text)
                        self._push(text)

            except Exception as exc:
                self.last_error = str(exc)
                logger.debug(
                    "Microphone/Vosk processing failed: %s",
                    exc,
                )

    def _push(self, text: str) -> None:
        text = (text or "").strip()

        if not text:
            return

        try:
            self._queue.put_nowait(text)
        except queue.Full:
            logger.debug(
                "Microphone queue is full; dropping %r.",
                text,
            )

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

    def _cleanup_audio(self) -> None:
        """Release PyAudio resources safely."""
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass

        try:
            if self._audio is not None:
                self._audio.terminate()
        except Exception:
            pass

        self._stream = None
        self._audio = None

    def close(self) -> None:
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=2.0)

        self._cleanup_audio()