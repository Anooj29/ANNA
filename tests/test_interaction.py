"""Wake-word, intent and dialogue tests."""

from __future__ import annotations

import pytest

from anna_robot.interaction.wake_word import (
    CommandRouter,
    Intent,
    WakeWordDetector,
    classify_intent,
    contains_phrase,
    normalize,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Hey Anna!", "hey anna"),
        ("HEY ANA", "hey anna"),
        ("hi, ana.", "hey anna"),
        ("ok anna", "hey anna"),
        ("um, please help", "help"),
        # "could you" is meaning, not filler - it stays.
        ("um, could you please help", "could you help"),
    ],
)
def test_normalize_canonicalises_homophones_and_filler(raw, expected):
    assert normalize(raw) == expected


def test_normalize_leaves_unrelated_words_alone():
    assert normalize("banana bread") == "banana bread"


def test_contains_phrase_matches_a_subsequence():
    assert contains_phrase("hey anna can we start the health check now", "start health check")
    assert not contains_phrase("health check start", "start health check")  # Order matters.


# -- wake words ---------------------------------------------------------
@pytest.mark.parametrize("phrase", ["hey anna", "yes anna", "hello anna", "yes buddy", "anna"])
def test_wake_phrases_are_recognised(phrase):
    matched, _ = WakeWordDetector().detect(phrase)
    assert matched is not None


def test_wake_word_needs_a_word_boundary():
    matched, _ = WakeWordDetector().detect("bananas are nice")
    assert matched is None


def test_wake_word_returns_the_rest_of_the_sentence():
    matched, remainder = WakeWordDetector().detect("Hey Anna, follow me please")
    assert matched == "hey anna"
    assert "follow me" in remainder


def test_longest_wake_phrase_wins():
    matched, _ = WakeWordDetector().detect("hey anna start")
    assert matched == "hey anna"


# -- intents ------------------------------------------------------------
@pytest.mark.parametrize(
    "text,intent",
    [
        ("start my health check", Intent.START_HEALTH_CHECK),
        ("check temperature", Intent.CHECK_TEMPERATURE),
        ("check pulse", Intent.CHECK_PULSE),
        ("check ecg", Intent.CHECK_ECG),
        ("follow me", Intent.FOLLOW_ME),
        ("stop following", Intent.STOP_FOLLOWING),
        ("stop", Intent.STOP),
        ("what do you see", Intent.WHAT_DO_YOU_SEE),
        ("who am i", Intent.WHO_AM_I),
        ("say that again", Intent.REPEAT),
        ("what can you do", Intent.HELP),
        ("yes", Intent.YES),
        ("no", Intent.NO),
        ("the weather is nice", Intent.CHAT),
        ("", Intent.NONE),
    ],
)
def test_intent_classification(text, intent):
    assert classify_intent(normalize(text)) is intent


def test_stop_following_is_not_an_emergency_stop():
    assert classify_intent("stop following me") is Intent.STOP_FOLLOWING


def test_legacy_yes_buddy_still_starts_a_health_check():
    """The original wording must keep working for existing users."""
    router = CommandRouter()
    utterance = router.parse("yes buddy")
    assert utterance.addressed_to_robot is True
    # "yes buddy" wakes ANNA; the state machine treats WAKE/YES as consent.
    assert utterance.intent in (Intent.WAKE, Intent.YES)


# -- routing and attention ----------------------------------------------
def test_wake_word_opens_an_attention_window():
    router = CommandRouter(attention_window_s=10.0)
    assert router.is_attentive is False
    router.parse("hey anna")
    assert router.is_attentive is True
    follow_up = router.parse("start my health check")
    assert follow_up.addressed_to_robot is True
    assert follow_up.intent is Intent.START_HEALTH_CHECK


def test_chatter_outside_the_window_is_ignored():
    router = CommandRouter()
    assert router.parse("the coffee machine is broken").addressed_to_robot is False


def test_emergency_stop_needs_no_wake_word():
    router = CommandRouter(require_wake_word=True)
    utterance = router.parse("stop")
    assert utterance.intent is Intent.STOP
    assert utterance.addressed_to_robot is True


def test_strict_mode_ignores_commands_without_a_wake_word():
    router = CommandRouter(require_wake_word=True)
    assert router.parse("check my pulse").addressed_to_robot is False
    router.parse("hey anna")
    assert router.parse("check my pulse").addressed_to_robot is True


def test_sleep_closes_the_window():
    router = CommandRouter()
    router.parse("hey anna")
    router.sleep()
    assert router.is_attentive is False


def test_parse_all_skips_blank_input():
    router = CommandRouter()
    assert len(router.parse_all(["hey anna", "", "   "])) == 1
