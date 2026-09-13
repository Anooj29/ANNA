"""State-machine enums and the health questionnaire definition."""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import NamedTuple, Optional, Tuple


class RobotState(str, Enum):
    STARTUP = "STARTUP"
    SEARCH = "SEARCH"            # Looking for someone to approach.
    INTERACT = "INTERACT"        # Someone is here; identify them.
    WAIT_CONFIRM = "WAIT_CONFIRM"  # Greeted; waiting for "start my health check".
    HEALTH_CHECK = "HEALTH_CHECK"  # Working through readings and questions.
    FOLLOW = "FOLLOW"            # Walking with the person ("follow me").
    DONE = "DONE"                # Session finished; pausing before the next.


class HealthStage(IntEnum):
    ASK_TEMP = 1
    WAIT_TEMP = 2
    ASK_PULSE = 3
    WAIT_PULSE = 4
    ASK_ECG = 5
    WAIT_ECG = 6
    ASK_QUESTION = 7
    WAIT_ANSWER = 8
    SUMMARISE = 9    # Waiting for the (background) Gemini summary.


class HealthQuestion(NamedTuple):
    key: str
    prompt: str
    label: str
    #: Words that make an answer plausible. Used to reject a stray command
    #: ("check my pulse") being recorded as the answer to "how did you sleep?".
    expects: Tuple[str, ...] = ()


#: Accepted spoken numbers, so "seven" is as good as "7".
NUMBER_WORDS: Tuple[str, ...] = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "none", "a few", "several", "many",
)

_YES_NO = ("yes", "no", "yeah", "nope", "yep", "nah", "a bit", "a little", "sometimes")

HEALTH_QUESTIONS: Tuple[HealthQuestion, ...] = (
    HealthQuestion(
        "sleep", "How many hours of sleep did you get last night? Please say a number.",
        "Sleep Hours", NUMBER_WORDS,
    ),
    HealthQuestion(
        "water", "How many glasses of water have you had today? Please say a number.",
        "Water Intake", NUMBER_WORDS,
    ),
    HealthQuestion(
        "pain", "Are you feeling any pain or discomfort today? Please say yes or no.",
        "Pain/Discomfort", _YES_NO,
    ),
    HealthQuestion(
        "appetite", "How is your appetite today? Please say good, poor, or normal.",
        "Appetite", ("good", "poor", "normal", "fine", "okay", "bad", "great"),
    ),
    HealthQuestion(
        "exercise", "Did you do any physical activity or exercise today? Please say yes or no.",
        "Exercise Today", _YES_NO + ("walk", "walked", "gym", "run", "ran"),
    ),
    HealthQuestion(
        "stress", "On a scale of one to ten, how stressed are you feeling today? Say a number.",
        "Stress Level", NUMBER_WORDS,
    ),
)


def question_for(index: int) -> Optional[HealthQuestion]:
    """The question at ``index``, or None once the list is exhausted."""
    if 0 <= index < len(HEALTH_QUESTIONS):
        return HEALTH_QUESTIONS[index]
    return None


def looks_like_answer(question: HealthQuestion, text: str) -> bool:
    """True when ``text`` plausibly answers ``question``.

    Any digit counts, as do the question's own expected words. Without this
    check the old code recorded whatever was said next - including other
    commands - as the patient's answer.
    """
    if not text:
        return False
    lowered = text.lower()
    if any(character.isdigit() for character in lowered):
        return True
    return any(word in lowered for word in question.expects)
