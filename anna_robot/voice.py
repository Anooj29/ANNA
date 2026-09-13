"""Text-to-speech wrapper using Piper."""

from __future__ import annotations

import logging
import subprocess
from .utils import clean_text

logger = logging.getLogger(__name__)


class VoiceAssistant:
    """
    Handles text-to-speech using the Piper TTS system.
    Piper is called as a subprocess that outputs raw audio to a player.
    """

    def __init__(self, piper_bin: str, piper_model: str) -> None:
        self._bin = piper_bin
        self._model = piper_model

    def speak(self, text: str) -> None:
        message = clean_text(text)
        logger.info("VOICE: %s", message)

        try:
            # Piper outputs raw PCM audio. We pipe it to 'aplay' (standard on RPi)
            # Command: echo "text" | piper --model model.onnx --output_raw | aplay -r 22050 -f S16_LE -t raw
            # Note: The sample rate (22050) might vary depending on the model.
            p1 = subprocess.Popen(
                ["echo", message],
                stdout=subprocess.PIPE,
                text=True
            )
            p2 = subprocess.Popen(
                [self._bin, "--model", self._model, "--output_raw"],
                stdin=p1.stdout,
                stdout=subprocess.PIPE
            )
            subprocess.run(["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw"], stdin=p2.stdout)

            p1.wait()
            p2.wait()

        except Exception:
            logger.exception("Piper TTS playback failed.")
