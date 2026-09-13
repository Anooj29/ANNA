"""State-machine enums and the health questionnaire definition."""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import NamedTuple, Tuple


class RobotState(str, Enum):
    STARTUP = "STARTUP"
    IDLE = "IDLE"
    SEARCH = "SEARCH"
    INTERACT = "INTERACT"
    WAIT_CONFIRM = "WAIT_CONFIRM"
    HEALTH_CHECK = "HEALTH_CHECK"
    DONE = "DONE"


class HealthStage(IntEnum):
    ASK_TEMP = 1
    WAIT_TEMP = 2
    ASK_PULSE = 3
    WAIT_PULSE = 4
    ASK_ECG = 5
    WAIT_ECG = 6
    ASK_QUESTION = 7
    WAIT_ANSWER = 8


class HealthQuestion(NamedTuple):
    key: str
    prompt: str
    label: str


HEALTH_QUESTIONS: Tuple[HealthQuestion, ...] = (
    HealthQuestion("sleep", "How many hours of sleep did you get last night? Please say a number.", "Sleep Hours"),
    HealthQuestion("water", "How many glasses of water have you had today? Please say a number.", "Water Intake"),
    HealthQuestion("pain", "Are you feeling any pain or discomfort today? Please say yes or no.", "Pain/Discomfort"),
    HealthQuestion("appetite", "How is your appetite today? Please say good, poor, or normal.", "Appetite"),
    HealthQuestion("exercise", "Did you do any physical activity or exercise today? Please say yes or no.", "Exercise Today"),
    HealthQuestion("stress", "On a scale of one to ten, how stressed are you feeling today? Say a number.", "Stress Level"),
)
