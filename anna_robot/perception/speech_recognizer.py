"""Local speech recognition using Vosk."""

from __future__ import annotations

import json
import queue
import threading
import logging
import sounddevice as sd
from vosk import Model, KaldiRecognizer

logger = logging.getLogger(__name__)


class SpeechRecognizer:
    """
    Listens to the microphone in a background thread and converts speech to text using Vosk.
    """

    def __init__(self, model_path: str, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate
        self._audio_queue = queue.Queue()

        try:
            logger.info("Loading Vosk model from %s...", model_path)
            self._model = Model(model_path)
            self._recognizer = KaldiRecognizer(self._model, self._sample_rate)
        except Exception:
            logger.exception("Failed to load Vosk model.")
            raise

        self._stop_event = threading.Event()
        self._command_queue = queue.Queue()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)

    def start(self) -> None:
        """Starts the microphone listener thread."""
        self._thread.start()
        logger.info("Speech recognition started.")

    def stop(self) -> None:
        """Stops the listener."""
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join()

    def get_command(self) -> str:
        """Returns the latest recognized command, or an empty string if none."""
        try:
            return self._command_queue.get_nowait().strip().lower()
        except queue.Empty:
            return ""

    def _microphone_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning("Audio status: %s", status)
        self._audio_queue.put(bytes(indata))

    def _listen_loop(self) -> None:
        """Background loop that processes audio and recognizes speech."""
        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                callback=self._microphone_callback,
                blocksize=8000
            ):
                while not self._stop_event.is_set():
                    try:
                        data = self._audio_queue.get(timeout=1.0)
                        if self._recognizer.AcceptWaveform(data):
                            result = json.loads(self._recognizer.Result())
                            text = result.get("text", "")
                            if text:
                                logger.info("Speech recognized: %s", text)
                                self._command_queue.put(text)
                    except queue.Empty:
                        continue
        except Exception:
            logger.exception("Speech recognition loop crashed.")
