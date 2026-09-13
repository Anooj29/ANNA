"""What ANNA says, and how she keeps a conversation coherent.

Keeping the wording here rather than scattered through the state machine
means the personality can be adjusted in one place, and that the state
machine reads as behaviour rather than as a script.

The manager also holds the few pieces of conversational memory ANNA needs:
what she last said (so "say that again" works), whether she is mid-question,
and how many times she has had to ask.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..voice import PRIORITY_NORMAL, VoiceAssistant
from .wake_word import Intent

logger = logging.getLogger(__name__)


def _pick(options: Sequence[str]) -> str:
    """Vary the phrasing so ANNA does not sound like a recording."""
    return random.choice(list(options))


ACKNOWLEDGEMENTS: Sequence[str] = (
    "Yes? I am listening.",
    "I am here. How can I help?",
    "Yes, I am listening.",
)

UNKNOWN_COMMAND: Sequence[str] = (
    "Sorry, I did not catch that. You can say, start my health check, or, follow me.",
    "I did not understand that one. Try saying, hey ANNA, start my health check.",
)

CAPABILITIES = (
    "I can recognise registered patients, take a temperature, pulse and E C G reading, "
    "ask a few health questions, follow you as you walk, and keep you in view while we talk. "
    "Say, hey ANNA, followed by what you need."
)


@dataclass
class DialogueManager:
    """Speaks on ANNA's behalf and remembers a little of the conversation."""

    voice: VoiceAssistant
    person_name: str = "there"
    _last_line: str = field(default="", init=False)
    _question_asked: Optional[str] = field(default=None, init=False)
    _repeat_count: Dict[str, int] = field(default_factory=dict, init=False)

    # -- basics -----------------------------------------------------------
    def say(self, text: str, priority: int = PRIORITY_NORMAL, dedupe: bool = True) -> bool:
        """Say something and remember it for a later "repeat that"."""
        if not text:
            return False
        self._last_line = text
        return self.voice.speak(text, priority=priority, dedupe=dedupe)

    def warn(self, text: str) -> bool:
        """A safety message: jumps the queue, never de-duplicated away."""
        self._last_line = text
        return self.voice.say_now(text)

    def repeat(self) -> bool:
        if not self._last_line:
            return self.say("I have not said anything yet.")
        return self.voice.speak(self._last_line, dedupe=False)

    @property
    def is_speaking(self) -> bool:
        return self.voice.is_speaking

    # -- conversation -----------------------------------------------------
    def acknowledge_wake(self) -> bool:
        return self.say(_pick(ACKNOWLEDGEMENTS), dedupe=False)

    def greet(self, name: str, greeting: str) -> bool:
        self.person_name = name
        return self.say(greeting, dedupe=False)

    def invite_health_check(self) -> bool:
        return self.say(
            "Whenever you are ready, say, hey ANNA, start my health check. "
            "You can also still say, yes buddy, to begin."
        )

    def ask(self, question: str, key: Optional[str] = None) -> bool:
        """Ask a question and remember that an answer is expected."""
        self._question_asked = key or question
        if key:
            self._repeat_count[key] = self._repeat_count.get(key, 0) + 1
        return self.say(question, dedupe=False)

    def reprompt(self, question: str, key: str) -> bool:
        """Ask again, more gently, when an answer did not arrive."""
        attempts = self._repeat_count.get(key, 0)
        if attempts >= 3:
            self.say("Let us move on for now.")
            return False
        self._repeat_count[key] = attempts + 1
        return self.say(f"Sorry, I did not catch that. {question}", dedupe=False)

    def confirm_answer(self) -> bool:
        return self.say(_pick(("Thank you.", "Got it, thank you.", "Noted, thank you.")), dedupe=False)

    def did_not_understand(self) -> bool:
        return self.say(_pick(UNKNOWN_COMMAND))

    def describe_capabilities(self) -> bool:
        return self.say(CAPABILITIES)

    def describe_scene(self, labels: Sequence[str]) -> bool:
        """Answer "what do you see?" from the current detections."""
        if not labels:
            return self.say("I cannot see anything I recognise right now.")
        counted: Dict[str, int] = {}
        for label in labels:
            counted[label] = counted.get(label, 0) + 1
        parts: List[str] = []
        for label, count in counted.items():
            parts.append(f"{count} {label}s" if count > 1 else f"a {label}")
        if len(parts) == 1:
            listed = parts[0]
        else:
            listed = ", ".join(parts[:-1]) + f" and {parts[-1]}"
        return self.say(f"I can see {listed}.", dedupe=False)

    def identify(self, name: Optional[str]) -> bool:
        if name and name != "--":
            return self.say(f"You are {name}. It is good to see you again.", dedupe=False)
        return self.say("I have not recognised you yet. Please look at my camera.")

    # -- movement commentary ---------------------------------------------
    def announce_following(self) -> bool:
        return self.say("Alright, I will follow you. Say, stop following, whenever you want me to wait.")

    def announce_stopped_following(self) -> bool:
        return self.say("I will wait here. Say, hey ANNA, follow me, when you want me again.")

    def announce_blocked(self) -> bool:
        return self.warn("I have stopped, something is close in front of me.")

    def announce_lost(self) -> bool:
        return self.say("I have lost sight of you. Could you step back in front of me?")

    def unknown_person(self, attempt: int) -> bool:
        lines = (
            "Sorry, I do not recognise you. I am only authorised to assist registered patients.",
            "I am afraid I cannot identify you. Please register with the healthcare system first.",
            "Hmm, your face is not in my database. Please contact the administrator to register.",
        )
        return self.say(lines[(max(attempt, 1) - 1) % len(lines)], dedupe=False)

    def fallback_for(self, intent: Intent) -> bool:
        """A sensible reply for an intent the current state cannot act on."""
        if intent == Intent.HELP:
            return self.describe_capabilities()
        if intent == Intent.REPEAT:
            return self.repeat()
        if intent == Intent.CANCEL:
            return self.say("Alright, cancelled.")
        if intent == Intent.WAKE:
            return self.acknowledge_wake()
        return self.did_not_understand()
