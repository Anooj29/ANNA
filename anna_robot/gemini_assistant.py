"""Gemini-powered greetings and wellness summaries, with safe fallbacks."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from google import genai

from .utils import clean_text

logger = logging.getLogger(__name__)


class GeminiAssistant:
    """Thin wrapper around the Gemini API for natural-language greetings and
    wellness summaries. Fails soft: any API error (or a missing API key)
    falls back to a canned, still-friendly response so the robot never goes
    silent mid-interaction."""

    _EMOTION_PROMPTS: Dict[str, str] = {
        "Happy": "The patient named {name} looks happy today. Give a warm 2 sentence friendly greeting and a positive comment about their mood. Keep it natural and conversational.",
        "Sad": "The patient named {name} looks sad today. Give a warm 2 sentence empathetic greeting that lifts their spirits. Keep it natural and caring.",
        "Angry": "The patient named {name} looks angry or stressed today. Give a calm 2 sentence soothing greeting. Keep it natural and calming.",
        "Neutral": "The patient named {name} looks calm and neutral today. Give a friendly 2 sentence greeting. Keep it natural.",
        "Fear": "The patient named {name} looks anxious or fearful today. Give a reassuring 2 sentence greeting. Keep it natural and comforting.",
        "Disgust": "The patient named {name} looks uncomfortable today. Give a gentle 2 sentence caring greeting. Keep it natural.",
        "Surprise": "The patient named {name} looks surprised today. Give a fun 2 sentence cheerful greeting. Keep it natural.",
    }

    def __init__(self, api_key: Optional[str], model_name: str) -> None:
        self._model_name = model_name
        self._client = None
        if api_key:
            try:
                self._client = genai.Client(api_key=api_key)
            except Exception:
                logger.exception("Failed to initialise the Gemini client; falling back to canned responses.")
        else:
            logger.warning("GEMINI_API_KEY is not set; Gemini features will use canned fallback responses.")

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
        template = self._EMOTION_PROMPTS.get(emotion, "Greet the patient named {name} warmly in 2 sentences.")
        result = self._generate(template.format(name=name))
        return result or f"Hello {name}. It is great to see you today. I am here to help with your health check."

    def health_summary(self, name: str, temperature: str, pulse: str, ecg: str, answers: Dict[str, str]) -> str:
        return self.health_summaries(name, temperature, pulse, ecg, answers)[1]

    def health_summaries(self, name: str, temperature: str, pulse: str, ecg: str, answers: Dict[str, str]) -> tuple[str, str]:
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
