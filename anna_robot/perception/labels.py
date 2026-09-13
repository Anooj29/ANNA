"""COCO label handling and the small set of objects ANNA cares about.

Detection models are trained on all 90 COCO classes, but reporting all of
them would bury the one that matters. ANNA therefore filters to a short
list - a person first and foremost, plus the furniture that describes the
room she is in - which also keeps the per-frame work small.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

#: Index -> name for the COCO classes ANNA can meaningfully use. The indices
#: are the standard SSD/COCO ids used by the TFLite detection zoo models.
COCO_LABELS: Dict[int, str] = {
    0: "person",
    56: "chair",
    57: "couch",
    59: "bed",
    60: "dining table",
    61: "toilet",
    62: "tv",
    63: "laptop",
    71: "sink",
    72: "refrigerator",
    73: "book",
    74: "clock",
}

#: What ANNA reports by default. Kept deliberately short: person is the one
#: that drives behaviour, and the rest are the furniture a ward or home has,
#: enough for context without adding per-frame cost.
DEFAULT_CLASSES_OF_INTEREST = ("person", "chair", "couch", "bed", "dining table", "tv")

PERSON_LABEL = "person"


def load_label_map(path: Optional[str] = None) -> Dict[int, str]:
    """Load a label file, falling back to the built-in COCO subset.

    Supports both common formats: one label per line (index = line number)
    and ``<index> <label>`` per line, which is what most TFLite model zips
    ship.
    """
    if not path or not os.path.exists(path):
        if path:
            logger.warning("Label file '%s' not found; using the built-in COCO labels.", path)
        return dict(COCO_LABELS)

    labels: Dict[int, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle):
                line = raw.strip()
                if not line:
                    continue
                head, _, tail = line.partition(" ")
                if tail and head.isdigit():
                    labels[int(head)] = tail.strip()
                else:
                    labels[line_number] = line
    except OSError:
        logger.exception("Could not read label file '%s'; using the built-in COCO labels.", path)
        return dict(COCO_LABELS)

    if "???" in labels.values():
        # Some label files pad unused ids with '???'; drop them so they can
        # never be reported as a detection.
        labels = {index: name for index, name in labels.items() if name != "???"}
    logger.info("Loaded %d labels from '%s'.", len(labels), path)
    return labels


def resolve_class_ids(labels: Dict[int, str], names: Iterable[str]) -> Dict[int, str]:
    """Map the wanted label names onto the ids this model actually uses."""
    wanted = {name.strip().lower() for name in names if name and name.strip()}
    if not wanted:
        return dict(labels)
    resolved = {index: name for index, name in labels.items() if name.lower() in wanted}
    missing = wanted - {name.lower() for name in resolved.values()}
    if missing:
        logger.warning(
            "These requested classes are not in the model's label map and will never be "
            "detected: %s", ", ".join(sorted(missing)),
        )
    return resolved


def parse_class_list(raw: Optional[str]) -> List[str]:
    """Parse a comma-separated class list from configuration."""
    if raw is None:
        return list(DEFAULT_CLASSES_OF_INTEREST)
    names = [part.strip() for part in raw.split(",") if part.strip()]
    return names or list(DEFAULT_CLASSES_OF_INTEREST)
