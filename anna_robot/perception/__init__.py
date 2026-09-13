"""Camera-based perception.

* :mod:`.object_detector` - multi-class TFLite detection (person first, plus
  the furniture ANNA reports for context).
* :mod:`.person_detector` - the person-only façade over that detector.
* :mod:`.tracker` - keeps one target locked between detections.
* :mod:`.face_identifier` - identifies a registered patient.
* :mod:`.emotion_detector` - reads the expression on a cropped face.
"""

from .emotion_detector import EmotionDetector, NullEmotionDetector
from .face_identifier import FaceIdentifier
from .labels import COCO_LABELS, DEFAULT_CLASSES_OF_INTEREST, PERSON_LABEL, parse_class_list
from .object_detector import Detection, ObjectDetector
from .person_detector import PersonDetector
from .tflite_backend import TfliteUnavailableError
from .tracker import TargetTracker, Track

__all__ = [
    "COCO_LABELS",
    "DEFAULT_CLASSES_OF_INTEREST",
    "Detection",
    "EmotionDetector",
    "FaceIdentifier",
    "NullEmotionDetector",
    "ObjectDetector",
    "PERSON_LABEL",
    "PersonDetector",
    "TargetTracker",
    "TfliteUnavailableError",
    "Track",
    "parse_class_list",
]
