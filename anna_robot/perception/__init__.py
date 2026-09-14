"""Camera-based perception: person detection, face ID, emotion detection."""

from .person_detector import PersonDetector
from .face_identifier import FaceIdentifier
from .emotion_detector import EmotionDetector

__all__ = ["PersonDetector", "FaceIdentifier", "EmotionDetector"]
from .speech_recognizer import SpeechRecognizer
