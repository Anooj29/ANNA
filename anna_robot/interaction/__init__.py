"""Speech and human interaction.

* :mod:`.wake_word` - "Hey ANNA" / "Yes ANNA" detection and intent parsing.
* :mod:`.dialogue` - everything ANNA says, and her short conversational memory.
* :mod:`.listener` - optional on-board microphone input.
"""

from .dialogue import DialogueManager
from .listener import MicrophoneListener
from .wake_word import (
    WAKE_PHRASES,
    CommandRouter,
    Intent,
    Utterance,
    WakeWordDetector,
    classify_intent,
    normalize,
)

__all__ = [
    "CommandRouter",
    "DialogueManager",
    "Intent",
    "MicrophoneListener",
    "Utterance",
    "WAKE_PHRASES",
    "WakeWordDetector",
    "classify_intent",
    "normalize",
]
