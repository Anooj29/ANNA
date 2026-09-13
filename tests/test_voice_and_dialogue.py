"""Tests for queued speech and the dialogue manager."""

from __future__ import annotations

import time


from anna_robot.interaction.dialogue import DialogueManager
from anna_robot.voice import PRIORITY_NORMAL, VoiceAssistant


class FakeVoice:
    """Records what would have been said, without any audio stack."""

    def __init__(self):
        self.said = []
        self.is_speaking = False

    def speak(self, text, priority=PRIORITY_NORMAL, dedupe=True):
        self.said.append(text)
        return True

    def say_now(self, text):
        self.said.append(text)
        return True


def test_speak_returns_immediately():
    voice = VoiceAssistant()
    started = time.monotonic()
    voice.speak("This is a reasonably long sentence to say out loud.")
    assert time.monotonic() - started < 0.1  # The control loop must not stall.
    voice.close()


def test_duplicate_lines_are_dropped_within_the_window():
    voice = VoiceAssistant(dedupe_window_s=60.0)
    assert voice.speak("Hello") is True
    assert voice.speak("Hello") is False
    assert voice.speak("Hello", dedupe=False) is True
    voice.close()


def test_empty_text_is_ignored():
    voice = VoiceAssistant()
    assert voice.speak("") is False
    assert voice.speak("   ") is False
    voice.close()


def test_queue_can_be_cleared():
    voice = VoiceAssistant()
    for index in range(5):
        voice.speak(f"Sentence number {index}")
    assert voice.clear_queue() >= 1
    voice.close()


# -- dialogue -----------------------------------------------------------
def test_describe_scene_reads_a_natural_list():
    voice = FakeVoice()
    DialogueManager(voice=voice).describe_scene(["person", "chair", "chair"])
    assert voice.said[-1] == "I can see a person and 2 chairs."


def test_describe_scene_with_nothing_visible():
    voice = FakeVoice()
    DialogueManager(voice=voice).describe_scene([])
    assert "cannot see anything" in voice.said[-1]


def test_repeat_says_the_last_line_again():
    voice = FakeVoice()
    dialogue = DialogueManager(voice=voice)
    dialogue.say("Please hold still.")
    dialogue.repeat()
    assert voice.said == ["Please hold still.", "Please hold still."]


def test_unknown_person_cycles_through_its_lines():
    voice = FakeVoice()
    dialogue = DialogueManager(voice=voice)
    for attempt in (1, 2, 3):
        dialogue.unknown_person(attempt)
    assert len(set(voice.said)) == 3


def test_reprompt_gives_up_after_three_attempts():
    voice = FakeVoice()
    dialogue = DialogueManager(voice=voice)
    question = "How did you sleep?"
    for _ in range(3):
        assert dialogue.reprompt(question, "sleep") is True
    assert dialogue.reprompt(question, "sleep") is False


def test_identify_handles_an_unknown_patient():
    voice = FakeVoice()
    DialogueManager(voice=voice).identify("--")
    assert "not recognised you" in voice.said[-1]
