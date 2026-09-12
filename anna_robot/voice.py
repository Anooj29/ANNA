"""Text-to-speech wrapper."""

from __future__ import annotations

import logging

import pyttsx3

from .utils import clean_text

logger = logging.getLogger(__name__)


class VoiceAssistant:
    """pyttsx3 on Linux (espeak driver) is known to become unresponsive if
    the same engine instance is reused for many say()/runAndWait() cycles in
    a long-running process. To keep the robot talking reliably for hours at
    a time, a fresh engine is created for each utterance by default; set
    reinit_each_call=False to keep a single persistent engine instead.
    """

    def __init__(self, rate: int = 145, reinit_each_call: bool = True) -> None:
        self._rate = rate
        self._reinit_each_call = reinit_each_call
        self._engine = None if reinit_each_call else self._new_engine()

    def _new_engine(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", self._rate)
        return engine

    def speak(self, text: str) -> None:
        message = clean_text(text)
        logger.info("VOICE: %s", message)
        engine = self._new_engine() if self._reinit_each_call else self._engine
        try:
            engine.say(message)
            engine.runAndWait()
        except Exception:
            logger.exception("Text-to-speech playback failed.")
        finally:
            if self._reinit_each_call:
                try:
                    engine.stop()
                except Exception:
                    pass
