"""Gemini-powered greetings and wellness summaries, with safe fallbacks.

Two things matter here beyond the prompts:

* **Nothing blocks the control loop.** A Gemini round trip takes seconds,
  and the original code made two of them inline - the robot was blind and
  deaf for that whole time. Requests now run on a worker thread and the
  state machine collects the result when it is ready
  (:meth:`request_greeting` / :meth:`take_greeting`).
* **It fails soft.** A missing key, a timeout or an API error falls back to
  canned, still-friendly text, so ANNA never goes silent mid-interaction.

The medical wording constraints in the prompts are deliberate and must stay:
this prototype's readings are not diagnostic.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Dict, Optional, Tuple

from .utils import clean_text

logger = logging.getLogger(__name__)


class GeminiAssistant:
    """Thin, non-blocking wrapper around the Gemini API."""

    _EMOTION_PROMPTS: Dict[str, str] = {
        "Happy": "The patient named {name} looks happy today. Give a warm 2 sentence friendly greeting and a positive comment about their mood. Keep it natural and conversational.",
        "Sad": "The patient named {name} looks sad today. Give a warm 2 sentence empathetic greeting that lifts their spirits. Keep it natural and caring.",
        "Angry": "The patient named {name} looks angry or stressed today. Give a calm 2 sentence soothing greeting. Keep it natural and calming.",
        "Neutral": "The patient named {name} looks calm and neutral today. Give a friendly 2 sentence greeting. Keep it natural.",
        "Fear": "The patient named {name} looks anxious or fearful today. Give a reassuring 2 sentence greeting. Keep it natural and comforting.",
        "Disgust": "The patient named {name} looks uncomfortable today. Give a gentle 2 sentence caring greeting. Keep it natural.",
        "Surprise": "The patient named {name} looks surprised today. Give a fun 2 sentence cheerful greeting. Keep it natural.",
    }

    def __init__(
        self,
        api_key: Optional[str],
        model_name: str,
        request_timeout_s: float = 12.0,
    ) -> None:
        self._model_name = model_name
        self._request_timeout_s = float(request_timeout_s)
        self._client = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemini")
        self._pending: Dict[str, Future] = {}

        if api_key:
            try:
                from google import genai  # type: ignore[import-not-found]

                self._client = genai.Client(api_key=api_key)
            except Exception:
                logger.exception("Failed to initialise the Gemini client; falling back to canned responses.")
        else:
            logger.warning("GEMINI_API_KEY is not set; Gemini features will use canned fallback responses.")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    # -- synchronous core -------------------------------------------------
    def _generate(self, prompt: str) -> Optional[str]:
        if self._client is None:
            return None
        try:
            response = self._client.models.generate_content(model=self._model_name, contents=prompt)
            return clean_text(response.text)
        except Exception:
            logger.exception("Gemini request failed.")
            return None

    def emotion_greeting(self, name: str, emotion: str) -> str:
        """Blocking greeting. Prefer :meth:`request_greeting` in the loop."""
        template = self._EMOTION_PROMPTS.get(emotion, "Greet the patient named {name} warmly in 2 sentences.")
        result = self._generate(template.format(name=name))
        return result or self.fallback_greeting(name)

    @staticmethod
    def fallback_greeting(name: str) -> str:
        return f"Hello {name}. It is great to see you today. I am here to help with your health check."

    def health_summary(self, name: str, temperature: str, pulse: str, ecg: str, answers: Dict[str, str]) -> str:
        return self.health_summaries(name, temperature, pulse, ecg, answers)[1]

    def health_summaries(
        self, name: str, temperature: str, pulse: str, ecg: str, answers: Dict[str, str]
    ) -> Tuple[str, str]:
        """Return distinct clinician and patient views of the same observation.

        Neither output may present this prototype's simulated/coarse readings
        as a diagnosis. A licensed clinician remains responsible for review.
        """
        answer_text = "\n".join(f"{question}: {answer}" for question, answer in answers.items())
        facts = (
            f"Patient name: {name}\n"
            f"Temperature: {temperature}\n"
            f"Pulse: {pulse}\n"
            f"ECG: {ecg}\n\n"
            f"Patient health questionnaire answers:\n{answer_text}\n"
        )
        clinical = self._generate(
            facts + "Write a concise clinical observation for a licensed clinician. Use precise neutral medical "
            "terminology only where supported by the listed data; state measured values, reported symptoms, and "
            "limitations. Do not diagnose, claim normality, infer disease, prescribe treatment, or state urgency. "
            "End with: 'Requires clinician review; prototype readings are not diagnostic.'"
        )
        patient = self._generate(
            facts + f"Write a kind, plain-language explanation addressed to {name}. Be reassuring without hiding "
            "uncertainty. Do not diagnose, say results are normal/stable, prescribe treatment, or give emergency "
            "advice. Explain that the care team will review the information and that this prototype cannot diagnose."
        )
        fallback_clinical = (
            f"ANNA visit observation: temperature {temperature}; pulse {pulse}; ECG note {ecg}. "
            "Questionnaire responses recorded. Requires clinician review; prototype readings are not diagnostic."
        )
        fallback_patient = (
            f"Hello {name}. ANNA has recorded your check-in information for your care team. "
            "This robot does not diagnose conditions, so please speak with your nurse or doctor about any concerns."
        )
        return clinical or fallback_clinical, patient or fallback_patient

    def small_talk(self, name: str, question: str) -> str:
        """A short spoken reply to a free-form question from the patient."""
        result = self._generate(
            f"You are ANNA, a friendly hospital assistant robot talking to {name}. "
            f"They said: '{question}'. Reply in at most two short spoken sentences. "
            "Be warm and practical. Do not give medical advice, diagnoses or treatment suggestions; "
            "if they ask for medical advice, say their care team is the right person to ask."
        )
        return result or "I am not sure about that one, but your care team will be able to help."

    # -- non-blocking interface -------------------------------------------
    def _submit(self, key: str, function, *args) -> None:
        """Start (or keep) one background request under ``key``."""
        with self._lock:
            pending = self._pending.get(key)
            if pending is not None and not pending.done():
                return  # Already in flight; do not pile up duplicates.
            self._pending[key] = self._executor.submit(function, *args)

    def _take(self, key: str, timeout: float = 0.0):
        """Collect a finished result, or None while it is still running."""
        with self._lock:
            pending = self._pending.get(key)
        if pending is None:
            return None
        if not pending.done() and timeout <= 0.0:
            return None
        try:
            result = pending.result(timeout=timeout)
        except Exception:
            logger.exception("Background Gemini request failed.")
            result = None
        with self._lock:
            self._pending.pop(key, None)
        return result

    def request_greeting(self, name: str, emotion: str) -> None:
        """Start generating a greeting in the background."""
        self._submit("greeting", self.emotion_greeting, name, emotion)

    def take_greeting(self, name: str) -> Optional[str]:
        """The greeting once ready, else None. Never blocks."""
        if not self.is_available:
            return self.fallback_greeting(name)
        return self._take("greeting")

    def request_summaries(
        self, name: str, temperature: str, pulse: str, ecg: str, answers: Dict[str, str]
    ) -> None:
        """Start generating both health summaries in the background."""
        self._submit("summaries", self.health_summaries, name, temperature, pulse, ecg, answers)

    def take_summaries(self) -> Optional[Tuple[str, str]]:
        return self._take("summaries")

    def request_small_talk(self, name: str, question: str) -> None:
        self._submit("chat", self.small_talk, name, question)

    def take_small_talk(self) -> Optional[str]:
        return self._take("chat")

    def is_pending(self, key: str) -> bool:
        with self._lock:
            pending = self._pending.get(key)
            return pending is not None and not pending.done()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
