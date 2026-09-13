"""Text-to-speech that never blocks the control loop.

The original implementation called ``pyttsx3.runAndWait()`` inline, which
stops the world for as long as the sentence takes to say - seconds during
which the robot could not see, steer, track a face or read its distance
sensor. Here every utterance goes onto a queue and a worker thread speaks
it, so the control loop keeps running at full rate while ANNA talks.

Also handled:

* **Priority** - a safety announcement jumps the queue.
* **De-duplication** - the state machine is called many times per second, so
  the same line is naturally requested repeatedly; a repeat inside
  ``dedupe_window_s`` is dropped instead of stuttering.
* **Engine health** - pyttsx3 on Linux (espeak) becomes unresponsive when
  one engine instance is reused for hours, so a fresh engine per utterance
  remains the default, exactly as before.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .utils import clean_text

logger = logging.getLogger(__name__)

#: Priorities. Lower numbers are spoken first.
PRIORITY_SAFETY = 0
PRIORITY_NORMAL = 5
PRIORITY_CHATTER = 9


@dataclass(order=True)
class _Utterance:
    priority: int
    sequence: int
    text: str = field(compare=False)


#: Shutdown sentinel. It must be a real ``_Utterance`` because a
#: PriorityQueue orders its items, and ``None`` cannot be ordered against
#: one. The lowest priority makes it jump the queue on close.
_SHUTDOWN = _Utterance(priority=-1, sequence=-1, text="")


class VoiceAssistant:
    """Queued, non-blocking speech.

    :meth:`speak` returns immediately. Use :attr:`is_speaking` to hold off
    on conversational steps until ANNA has finished a sentence, and
    :meth:`wait_until_idle` only where blocking really is wanted (shutdown).
    """

    def __init__(
        self,
        rate: int = 145,
        reinit_each_call: bool = True,
        volume: float = 1.0,
        voice_id: Optional[str] = None,
        dedupe_window_s: float = 4.0,
        max_queue: int = 16,
    ) -> None:
        self._rate = int(rate)
        self._volume = float(volume)
        self._voice_id = voice_id
        self._reinit_each_call = bool(reinit_each_call)
        self._dedupe_window_s = float(dedupe_window_s)

        self._queue: "queue.PriorityQueue[_Utterance]" = queue.PriorityQueue(maxsize=max_queue)
        self._sequence = 0
        self._lock = threading.Lock()
        self._speaking = threading.Event()
        self._stopped = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._recent: dict = {}
        self.last_spoken = ""

        self._pyttsx3 = self._import_engine_module()
        self._engine = None if (self._reinit_each_call or self._pyttsx3 is None) else self._new_engine()
        self._worker = threading.Thread(target=self._run, name="voice", daemon=True)
        self._worker.start()

    # -- engine -----------------------------------------------------------
    @staticmethod
    def _import_engine_module():
        try:
            import pyttsx3  # type: ignore[import-not-found]

            return pyttsx3
        except Exception as exc:  # pragma: no cover - depends on the machine
            logger.warning(
                "pyttsx3 is unavailable (%s). Speech will be logged instead of spoken; "
                "install pyttsx3 and the 'espeak' system package to hear ANNA.", exc,
            )
            return None

    def _new_engine(self):
        engine = self._pyttsx3.init()
        engine.setProperty("rate", self._rate)
        engine.setProperty("volume", self._volume)
        if self._voice_id:
            try:
                engine.setProperty("voice", self._voice_id)
            except Exception:
                logger.warning("Requested TTS voice '%s' is not available.", self._voice_id)
        return engine

    # -- public API -------------------------------------------------------
    @property
    def is_speaking(self) -> bool:
        """True while a sentence is being spoken or is waiting to be."""
        return self._speaking.is_set() or not self._queue.empty()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def speak(self, text: str, priority: int = PRIORITY_NORMAL, dedupe: bool = True) -> bool:
        """Queue a sentence. Returns False if it was dropped.

        Never blocks and never raises: a failure to speak must not be able
        to stop the robot.
        """
        message = clean_text(text)
        if not message:
            return False
        if dedupe and self._is_repeat(message):
            logger.debug("Skipping repeated utterance: %s", message)
            return False

        with self._lock:
            self._sequence += 1
            item = _Utterance(priority=priority, sequence=self._sequence, text=message)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            logger.warning("Speech queue is full; dropping: %s", message)
            return False
        self._idle.clear()
        logger.info("VOICE: %s", message)
        return True

    def say_now(self, text: str) -> bool:
        """Speak as soon as possible, ahead of anything already queued."""
        return self.speak(text, priority=PRIORITY_SAFETY, dedupe=False)

    def _is_repeat(self, message: str) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._recent.get(message)
            self._recent = {
                text: when for text, when in self._recent.items()
                if now - when < self._dedupe_window_s
            }
            self._recent[message] = now
        return last is not None and (now - last) < self._dedupe_window_s

    def wait_until_idle(self, timeout: Optional[float] = None) -> bool:
        """Block until the queue drains. Only for shutdown and tests."""
        return self._idle.wait(timeout)

    def clear_queue(self) -> int:
        """Drop everything still waiting (the current sentence finishes)."""
        dropped = 0
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                dropped += 1
            except queue.Empty:
                break
        return dropped

    # -- worker -----------------------------------------------------------
    def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                if not self._speaking.is_set():
                    self._idle.set()
                continue
            if item is _SHUTDOWN:
                self._queue.task_done()
                break
            self._speaking.set()
            try:
                self._render(item.text)
                self.last_spoken = item.text
            except Exception:
                logger.exception("Text-to-speech playback failed.")
            finally:
                self._speaking.clear()
                self._queue.task_done()
                if self._queue.empty():
                    self._idle.set()

    def _render(self, message: str) -> None:
        if self._pyttsx3 is None:
            # No engine: the message has already been logged, so behave as
            # though it were spoken (roughly in real time) rather than
            # racing silently ahead of the conversation.
            time.sleep(min(len(message) / 15.0, 6.0))
            return
        engine = self._new_engine() if self._reinit_each_call else self._engine
        try:
            engine.say(message)
            engine.runAndWait()
        finally:
            if self._reinit_each_call:
                try:
                    engine.stop()
                except Exception:
                    logger.debug("TTS engine failed to stop cleanly.", exc_info=True)

    def close(self, timeout: float = 3.0) -> None:
        """Finish the current sentence, then stop the worker thread."""
        self._stopped.set()
        try:
            self._queue.put_nowait(_SHUTDOWN)
        except queue.Full:
            pass
        self._worker.join(timeout=timeout)
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                logger.debug("TTS engine failed to stop cleanly.", exc_info=True)
