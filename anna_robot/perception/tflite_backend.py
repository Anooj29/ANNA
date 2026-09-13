"""One place that finds a TFLite runtime, so the models do not each guess.

``tflite_runtime`` is the small wheel used on a Pi; a development machine is
more likely to have full TensorFlow. Both expose the same ``Interpreter``,
so this picks whichever is installed and reports a clear, actionable error
when neither is.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_interpreter_factory: Optional[Any] = None
_runtime_name = "none"


class TfliteUnavailableError(RuntimeError):
    """Raised when no TFLite runtime can be imported."""


def load_interpreter_factory() -> Any:
    """Return the ``Interpreter`` class from whichever runtime is installed."""
    global _interpreter_factory, _runtime_name
    if _interpreter_factory is not None:
        return _interpreter_factory
    try:
        import tflite_runtime.interpreter as tflite  # type: ignore[import-not-found]

        _interpreter_factory, _runtime_name = tflite.Interpreter, "tflite_runtime"
    except ImportError:
        try:
            import tensorflow as tf  # type: ignore[import-not-found]

            _interpreter_factory, _runtime_name = tf.lite.Interpreter, "tensorflow.lite"
        except ImportError as exc:
            raise TfliteUnavailableError(
                "No TFLite runtime found. Install 'tflite-runtime' (Raspberry Pi) or "
                "'tensorflow' (desktop):\n"
                "  pip install tflite-runtime --extra-index-url https://google-coral.github.io/py-repo/"
            ) from exc
    logger.info("TFLite runtime: %s", _runtime_name)
    return _interpreter_factory


def runtime_name() -> str:
    return _runtime_name


def quantize(data: np.ndarray, detail: dict) -> np.ndarray:
    """Convert float image data into the tensor's own dtype.

    Quantised (uint8/int8) models carry a scale and zero point; ignoring
    them - as the original code did - feeds the network garbage and it
    silently detects nothing. Float models are passed through normalised.
    """
    dtype = detail["dtype"]
    if dtype == np.float32:
        return data.astype(np.float32)
    scale, zero_point = detail.get("quantization", (0.0, 0))
    if scale:
        return np.clip(data / scale + zero_point, np.iinfo(dtype).min, np.iinfo(dtype).max).astype(dtype)
    return data.astype(dtype)


def dequantize(data: np.ndarray, detail: dict) -> np.ndarray:
    """Convert a raw output tensor back to floats using its quant params."""
    scale, zero_point = detail.get("quantization", (0.0, 0))
    if scale:
        return (data.astype(np.float32) - zero_point) * scale
    return data.astype(np.float32)


def input_scaling(detail: dict) -> Tuple[float, float]:
    """Return (mean, std) normalisation for a float input tensor.

    Detection models exported by the TFLite Model Maker expect [-1, 1];
    classifiers usually want [0, 1]. The model's own quantisation metadata
    tells us which, when it is present.
    """
    quant = detail.get("quantization", (0.0, 0))
    if detail["dtype"] == np.float32 and quant and quant[0] == 0:
        return 127.5, 127.5
    return 0.0, 255.0
