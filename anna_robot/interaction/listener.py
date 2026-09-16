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

    Set ``ROBOT_MIC_ENABLED=true`` to switch it on (``ROBOT_MIC_DEVICE_NAME`` or
    ``ROBOT_MIC_DEVICE_INDEX`` choose the device), and install the extras:
    ``pip install SpeechRecognition PyAudio`` (plus ``sudo apt install
    portaudio19-dev`` on a Pi).
    """

    def __init__(
        self,
        enabled: bool = False,
        device_index: Optional[int] = None,
        device_name: Optional[str] = None,
        sample_rate: Optional[int] = None,
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
        self.device_index: Optional[int] = device_index
        self.last_error: Optional[str] = None

        if not self.enabled:
            return
        try:
            import speech_recognition as sr  # type: ignore[import-not-found]

            if self.device_index is None:
                self.device_index = self._find_input_device(device_name)
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = int(energy_threshold)
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = float(pause_threshold)
            self._microphone = sr.Microphone(device_index=self.device_index, sample_rate=sample_rate)
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
        logger.info("Microphone listening is active (device index %s).", self.device_index)

    @staticmethod
    def _find_input_device(device_name: Optional[str]) -> Optional[int]:
        """Pick an input device, preferring one whose name matches.

        On a Pi the default audio device is usually the HDMI/headphone
        output, which has no input channels, so a microphone built into a USB
        camera is never heard unless it is selected explicitly. Without
        ``device_name`` the first device that looks like a camera/USB mic wins.
        """
        try:
            import pyaudio  # type: ignore[import-not-found]

            audio = pyaudio.PyAudio()
            try:
                devices = [audio.get_device_info_by_index(i) for i in range(audio.get_device_count())]
            finally:
                audio.terminate()
        except Exception:
            logger.debug("Could not list audio devices.", exc_info=True)
            return None

        inputs = [
            (int(info["index"]), str(info.get("name", "")))
            for info in devices
            if int(info.get("maxInputChannels", 0)) > 0
        ]
        logger.info(
            "Audio input devices: %s",
            ", ".join(f"[{index}] {name}" for index, name in inputs) or "none",
        )
        if not inputs:
            logger.warning("No audio input device found - is the camera's microphone connected?")
            return None

        keywords = [device_name.lower()] if device_name else ["camera", "webcam", "cam", "usb", "mic"]
        for keyword in keywords:
            for index, name in inputs:
                if keyword in name.lower():
                    logger.info("Using microphone [%d] %s.", index, name)
                    return index
        index, name = inputs[0]
        logger.info("No named match; using microphone [%d] %s.", index, name)
        return index

    def _run(self) -> None:  # pragma: no cover - needs real audio hardware
        # Keep one stream open. Re-opening a USB audio device for every phrase
        # is slow on a Pi and clips the start of what was said.
        while not self._stop.is_set():
            try:
                with self._microphone as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
                    logger.info(
                        "Microphone calibrated (energy threshold %.0f).",
                        self._recognizer.energy_threshold,
                    )
                    self._listen(source)
            except Exception as exc:
                self.last_error = str(exc)
                logger.error(
                    "Microphone stream failed (%s); retrying in 5 s. If this repeats, set "
                    "ROBOT_MIC_DEVICE_INDEX or ROBOT_MIC_SAMPLE_RATE (e.g. 48000).",
                    exc,
                )
                self._stop.wait(5.0)

    def _listen(self, source) -> None:  # pragma: no cover - needs real audio hardware
        while not self._stop.is_set():
            try:
                audio = self._recognizer.listen(
                    source, timeout=2.0, phrase_time_limit=self.phrase_time_limit
                )
            except self._sr.WaitTimeoutError:
                continue  # The normal "nobody spoke" case.
            try:
                text = self._recognizer.recognize_google(audio, language=self.language)
            except self._sr.UnknownValueError:
                logger.debug("Heard sound but could not make out any words.")
                continue
            except self._sr.RequestError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "Speech recognition service unreachable (%s); it needs an internet connection.",
                    exc,
                )
                continue
            logger.info("Microphone heard: %r", text)
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
