"""Detection tests: tensor layout, class filtering, and box safety."""

from __future__ import annotations

import numpy as np
import pytest

from anna_robot.perception.labels import (
    COCO_LABELS,
    DEFAULT_CLASSES_OF_INTEREST,
    load_label_map,
    parse_class_list,
    resolve_class_ids,
)
from anna_robot.perception.object_detector import ObjectDetector

from .fake_tflite import make_detector

FRAME = np.zeros((480, 640, 3), np.uint8)

PERSON = (0, 0.93, [0.1, 0.2, 0.9, 0.5])
CHAIR = (56, 0.72, [0.5, 0.6, 0.8, 0.9])
BED = (59, 0.81, [0.2, 0.1, 0.6, 0.4])
LOW_SCORE_PERSON = (0, 0.20, [0.1, 0.1, 0.2, 0.2])
OFF_FRAME = (0, 0.99, [-0.3, -0.4, -0.001, -0.002])
TOOTHBRUSH = (89, 0.95, [0.1, 0.1, 0.5, 0.5])


def test_output_tensors_are_identified_by_shape_not_index():
    """The fake model shuffles its outputs; detection must still work."""
    detector = make_detector([PERSON])
    assert detector._tensor_roles["boxes"] == 1
    assert detector._tensor_roles["scores"] == 3
    assert detector._tensor_roles["classes"] == 0
    detections = detector.detect(FRAME)
    assert [d.label for d in detections] == ["person"]


def test_detects_person_and_furniture():
    detector = make_detector([PERSON, CHAIR, BED], score_threshold=0.5)
    labels = {d.label for d in detector.detect(FRAME)}
    assert labels == {"person", "chair", "bed"}


def test_classes_outside_the_watch_list_are_ignored():
    detector = make_detector([PERSON, TOOTHBRUSH], score_threshold=0.5)
    assert [d.label for d in detector.detect(FRAME)] == ["person"]


def test_low_scoring_detections_are_dropped():
    detector = make_detector([PERSON, LOW_SCORE_PERSON], score_threshold=0.5)
    assert len(detector.detect(FRAME)) == 1


def test_boxes_are_clipped_to_the_frame():
    detector = make_detector([PERSON], score_threshold=0.5)
    xmin, ymin, xmax, ymax = detector.detect(FRAME)[0].box
    assert 0 <= xmin < xmax <= 640
    assert 0 <= ymin < ymax <= 480


def test_degenerate_off_frame_boxes_are_discarded():
    """A box entirely outside the frame would crop to nothing downstream."""
    detector = make_detector([OFF_FRAME], score_threshold=0.5)
    assert detector.detect(FRAME) == []


def test_results_are_sorted_by_score():
    detector = make_detector([CHAIR, PERSON, BED], score_threshold=0.5)
    scores = [d.score for d in detector.detect(FRAME)]
    assert scores == sorted(scores, reverse=True)


def test_duplicate_boxes_of_one_class_are_suppressed():
    near_duplicate = (0, 0.88, [0.11, 0.21, 0.89, 0.51])
    detector = make_detector([PERSON, near_duplicate], score_threshold=0.5)
    assert len(detector.detect(FRAME)) == 1


def test_quantised_models_get_their_input_quantised():
    from unittest import mock

    import anna_robot.perception.object_detector as module

    from .fake_tflite import FakeSsdInterpreter

    interpreter = type("Q", (FakeSsdInterpreter,), {"detections": (PERSON,), "quantised": True})
    with mock.patch.object(module, "load_interpreter_factory", return_value=interpreter), \
            mock.patch("os.path.exists", return_value=True):
        detector = module.ObjectDetector("fake.tflite", score_threshold=0.5)
    detector.detect(FRAME)
    assert detector._interpreter.last_input.dtype == np.uint8


def test_float_models_get_normalised_input():
    detector = make_detector([PERSON])
    detector.detect(np.full((480, 640, 3), 255, np.uint8))
    data = detector._interpreter.last_input
    assert data.dtype == np.float32
    assert data.max() <= 1.0001  # Scaled to [-1, 1], not left as 0..255.


def test_best_person_prefers_the_nearest_most_confident():
    from anna_robot.perception.object_detector import Detection

    far = Detection("person", 0.9, (0, 0, 20, 40))
    near = Detection("person", 0.8, (0, 0, 200, 400))
    assert ObjectDetector.best_person([far, near]) is near


def test_best_person_returns_none_without_people():
    from anna_robot.perception.object_detector import Detection

    assert ObjectDetector.best_person([Detection("chair", 0.9, (0, 0, 10, 10))]) is None


def test_detect_people_filters_to_people():
    detector = make_detector([PERSON, CHAIR], score_threshold=0.5)
    assert all(d.is_person for d in detector.detect_people(FRAME))


def test_empty_frame_is_handled():
    detector = make_detector([PERSON])
    assert detector.detect(np.empty((0, 0, 3), np.uint8)) == []


def test_missing_model_file_raises_a_clear_error():
    with pytest.raises(FileNotFoundError, match="models/README"):
        ObjectDetector("definitely/not/here.tflite")


# -- labels -------------------------------------------------------------
def test_default_classes_include_person_and_furniture():
    assert "person" in DEFAULT_CLASSES_OF_INTEREST
    assert {"chair", "bed"} <= set(DEFAULT_CLASSES_OF_INTEREST)


def test_resolve_class_ids_maps_names_to_model_ids():
    resolved = resolve_class_ids(COCO_LABELS, ["person", "bed"])
    assert resolved == {0: "person", 59: "bed"}


def test_unknown_class_names_are_warned_about_not_fatal():
    assert resolve_class_ids(COCO_LABELS, ["person", "unicorn"]) == {0: "person"}


def test_parse_class_list_falls_back_to_the_default():
    assert parse_class_list(None) == list(DEFAULT_CLASSES_OF_INTEREST)
    assert parse_class_list("  ") == list(DEFAULT_CLASSES_OF_INTEREST)
    assert parse_class_list("person, bed") == ["person", "bed"]


def test_label_file_formats(tmp_path):
    indexed = tmp_path / "indexed.txt"
    indexed.write_text("0 person\n56 chair\n")
    assert load_label_map(str(indexed)) == {0: "person", 56: "chair"}

    plain = tmp_path / "plain.txt"
    plain.write_text("person\n???\nchair\n")
    labels = load_label_map(str(plain))
    assert labels[0] == "person" and labels[2] == "chair"
    assert "???" not in labels.values()


def test_missing_label_file_falls_back_to_builtin():
    assert load_label_map("/nope/labels.txt") == COCO_LABELS
