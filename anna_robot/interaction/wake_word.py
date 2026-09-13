"""Wake-word detection and intent parsing for spoken commands.

ANNA answers to **"Hey ANNA"** and **"Yes ANNA"**. Saying either opens a
short attentive window during which she accepts commands without being
addressed again - so "Hey ANNA... start my health check" works as two
utterances, the way people actually talk.

Everything in this module is plain text processing with no audio
dependencies, which keeps it fast, fully unit-testable, and usable with any
speech source: the companion app over TCP, an on-board microphone, or a
dashboard.

Recogniser output is messy, so matching is deliberately forgiving:

* homophones are normalised ("hey ana", "hi anna", "a n a" -> "hey anna");
* filler words and punctuation are stripped;
* phrases match by token subsequence, so "hey anna could you please start my
  health check" still resolves to one clean intent.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

ROBOT_NAME = "anna"

#: Speech recognisers mishear the robot's name constantly. Each pattern is
#: rewritten to the canonical name before anything else is matched.
_NAME_HOMOPHONES = re.compile(
    r"\b(?:ana|anne|anya|hanna|hannah|ann[ae]?|amma|alanna|ohana|on[ae]|a\s*n\s*n?\s*a)\b"
)
_GREETING_HOMOPHONES = re.compile(r"\b(?:hay|hei|heyy+|hi|hii+|hello|helo|ok|okay|okey|yo)\b")
_YES_WORDS = re.compile(r"\b(?:yes|yeah|yep|yup|ya|sure|okay|ok|affirmative|correct|right|go ahead|please do)\b")
_NO_WORDS = re.compile(r"\b(?:no|nope|nah|negative|not now|later)\b")
# Only true filler is stripped. Phrases like "can you" are left alone:
# they carry meaning ("what can you do") and the subsequence matcher
# already tolerates the extra words around a command.
_FILLER = re.compile(r"\b(?:um+|uh+|er+|hmm+|like|just|please|kindly)\b")
_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lower-case, de-punctuate and canonicalise a recognised utterance."""
    if not text:
        return ""
    text = _PUNCTUATION.sub(" ", text.lower())
    text = _NAME_HOMOPHONES.sub(ROBOT_NAME, text)
    text = _GREETING_HOMOPHONES.sub("hey", text)
    text = _FILLER.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    """True when every word of ``phrase`` appears in ``text``, in order.

    Subsequence rather than substring matching is what lets "hey anna can we
    start the health check now" match the phrase "start health check"
    without needing a rule for every way of padding it.
    """
    words = text.split()
    needle = phrase.split()
    if not needle:
        return False
    position = 0
    for word in words:
        if word == needle[position]:
            position += 1
            if position == len(needle):
                return True
    return False


class Intent(str, Enum):
    """What the person asked for, independent of how they phrased it."""

    NONE = "NONE"
    WAKE = "WAKE"                        # "Hey ANNA" with nothing after it.
    START_HEALTH_CHECK = "START_HEALTH_CHECK"
    CHECK_TEMPERATURE = "CHECK_TEMPERATURE"
    CHECK_PULSE = "CHECK_PULSE"
    CHECK_ECG = "CHECK_ECG"
    FOLLOW_ME = "FOLLOW_ME"
    STOP_FOLLOWING = "STOP_FOLLOWING"
    STOP = "STOP"                        # Emergency "stop!"
    REPEAT = "REPEAT"
    CANCEL = "CANCEL"
    WHO_AM_I = "WHO_AM_I"
    WHAT_DO_YOU_SEE = "WHAT_DO_YOU_SEE"
    HELP = "HELP"
    YES = "YES"
    NO = "NO"
    CHAT = "CHAT"                        # Anything else, addressed to ANNA.


#: Wake phrases. "yes buddy" is kept from the original build so existing
#: scripts and anybody used to the old wording keep working.
WAKE_PHRASES: Tuple[str, ...] = (
    "hey anna",
    "yes anna",
    "hello anna",
    "anna",
    "yes buddy",
    "hey buddy",
)

#: Intent phrases, checked in order. The first match wins, so put the more
#: specific phrasings first.
INTENT_PHRASES: Tuple[Tuple[Intent, Tuple[str, ...]], ...] = (
    # "stop following" must be tested before the bare "stop", or every
    # request to stop following would read as an emergency stop.
    (Intent.STOP_FOLLOWING, ("stop following", "stop follow", "dont follow", "do not follow", "stay here", "wait here")),
    (Intent.STOP, ("stop moving", "stop right there", "emergency stop", "halt", "freeze", "stop")),
    (Intent.FOLLOW_ME, ("follow me", "come with me", "walk with me", "come along", "follow")),
    (Intent.CHECK_TEMPERATURE, ("check temperature", "check my temperature", "take my temperature", "temperature")),
    (Intent.CHECK_PULSE, ("check pulse", "check my pulse", "take my pulse", "heart rate", "pulse")),
    (Intent.CHECK_ECG, ("check ecg", "check my ecg", "record ecg", "ecg", "e c g")),
    (Intent.START_HEALTH_CHECK, (
        "start health check", "start my health check", "begin health check", "health check",
        "start checkup", "check up", "start check", "im ready", "i am ready", "lets start", "start",
    )),
    (Intent.WHAT_DO_YOU_SEE, ("what do you see", "what can you see", "what is around", "describe the room")),
    (Intent.WHO_AM_I, ("who am i", "do you know me", "do you recognise me", "do you recognize me", "my name")),
    (Intent.REPEAT, ("say that again", "repeat that", "repeat", "pardon", "what did you say")),
    (Intent.HELP, ("what can you do", "help me", "help")),
    (Intent.CANCEL, ("cancel", "never mind", "nevermind", "forget it")),
)


@dataclass
class Utterance:
    """One recognised phrase, after parsing."""

    raw: str
    text: str
    intent: Intent
    addressed_to_robot: bool
    wake_word: Optional[str] = None
    #: Whatever followed the wake word, e.g. "start my health check".
    remainder: str = ""
    timestamp: float = field(default_factory=time.monotonic)

    @property
    def is_actionable(self) -> bool:
        return self.addressed_to_robot and self.intent not in (Intent.NONE, Intent.WAKE)

    @property
    def is_affirmative_wake(self) -> bool:
        """True for "yes ANNA" / "yes buddy" - a wake word that is also a yes.

        The original build started the health check on exactly "yes buddy",
        so where a confirmation is expected these phrases count as consent
        rather than as a bare "are you there?".
        """
        return bool(self.wake_word and self.wake_word.startswith("yes") and not self.remainder)

    def as_dict(self) -> Dict[str, object]:
        return {
            "text": self.text,
            "intent": self.intent.value,
            "addressed": self.addressed_to_robot,
            "wake_word": self.wake_word,
        }


class WakeWordDetector:
    """Finds a wake phrase and reports what was said after it."""

    def __init__(self, phrases: Sequence[str] = WAKE_PHRASES) -> None:
        # Longest first, so "hey anna" is preferred over the bare "anna".
        self.phrases = tuple(sorted({normalize(p) for p in phrases if p}, key=len, reverse=True))

    def detect(self, text: str) -> Tuple[Optional[str], str]:
        """Return ``(matched_phrase, remainder)``; ``(None, text)`` if absent."""
        normalized = normalize(text)
        for phrase in self.phrases:
            index = normalized.find(phrase)
            if index == -1:
                continue
            # Only match on a word boundary, so "banana" is not a wake word.
            before = normalized[:index]
            after = normalized[index + len(phrase):]
            if (not before or before.endswith(" ")) and (not after or after.startswith(" ")):
                return phrase, (before + " " + after).strip()
        return None, normalized


def classify_intent(text: str) -> Intent:
    """Map an already-normalised utterance onto an intent."""
    if not text:
        return Intent.NONE
    for intent, phrases in INTENT_PHRASES:
        if any(contains_phrase(text, phrase) for phrase in phrases):
            return intent
    # Bare yes/no only after the specific phrases, so "yes, check my pulse"
    # is treated as the pulse request rather than a plain confirmation.
    if _NO_WORDS.search(text):
        return Intent.NO
    if _YES_WORDS.search(text):
        return Intent.YES
    return Intent.CHAT


class CommandRouter:
    """Turns raw recogniser text into :class:`Utterance` objects.

    After a wake word, ANNA stays attentive for ``attention_window_s`` so a
    follow-up sentence does not have to repeat her name. Outside that window
    only the emergency "stop" is honoured without being addressed, because
    a person shouting "stop!" should never have to remember the wake word.
    """

    def __init__(
        self,
        attention_window_s: float = 12.0,
        wake_phrases: Sequence[str] = WAKE_PHRASES,
        require_wake_word: bool = False,
    ) -> None:
        self.attention_window_s = float(attention_window_s)
        self.require_wake_word = bool(require_wake_word)
        self.detector = WakeWordDetector(wake_phrases)
        self._attentive_until = 0.0
        self.last_utterance: Optional[Utterance] = None

    # -- attention --------------------------------------------------------
    @property
    def is_attentive(self) -> bool:
        return time.monotonic() < self._attentive_until

    def attention_remaining_s(self) -> float:
        return max(self._attentive_until - time.monotonic(), 0.0)

    def wake(self) -> None:
        """Open the attentive window (also used when ANNA asks a question)."""
        self._attentive_until = time.monotonic() + self.attention_window_s

    def sleep(self) -> None:
        self._attentive_until = 0.0

    # -- parsing ----------------------------------------------------------
    def parse(self, raw: str) -> Utterance:
        """Parse one utterance and update the attention window."""
        wake_phrase, remainder = self.detector.detect(raw)
        normalized = normalize(raw)
        intent = classify_intent(remainder if wake_phrase else normalized)

        if wake_phrase:
            self.wake()
            addressed = True
            if not remainder:
                intent = Intent.WAKE
        elif intent == Intent.STOP:
            # Safety word: always heard, wake word or not.
            addressed = True
        elif self.is_attentive:
            addressed = True
            self.wake()  # Conversation continues; extend the window.
        else:
            addressed = not self.require_wake_word and intent != Intent.CHAT

        utterance = Utterance(
            raw=raw,
            text=normalized,
            intent=intent,
            addressed_to_robot=addressed,
            wake_word=wake_phrase,
            remainder=remainder if wake_phrase else normalized,
        )
        self.last_utterance = utterance
        logger.debug("Parsed %r -> %s", raw, utterance.as_dict())
        return utterance

    def parse_all(self, utterances: Iterable[str]) -> List[Utterance]:
        return [self.parse(text) for text in utterances if text and text.strip()]
