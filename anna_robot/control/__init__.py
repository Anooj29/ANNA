"""Feedback control: PID loops and the feedback sources that drive them.

The package is deliberately split by *feedback modality* so each can be
tuned, tested and enabled independently:

* :mod:`.visual` - camera feedback. Active today; it is what ANNA follows.
* :mod:`.encoder` - wheel-encoder odometry. Fully implemented, disabled by
  default until encoders are fitted.
* :mod:`.imu` - IMU heading/yaw-rate. Same: implemented, disabled by default.

:mod:`.feedback` is the common contract between them, :mod:`.pid` is the one
shared controller, and :mod:`.follower` is the person-following behaviour
built on top.
"""

from .encoder import EncoderGeometry, WheelEncoderFeedback
from .feedback import BaseFeedbackSource, FeedbackBus, FeedbackSource, MotionEstimate
from .follower import (
    DEFAULT_BEARING_GAINS,
    DEFAULT_RANGE_GAINS,
    DriveCommand,
    FollowState,
    FollowTuning,
    PersonFollower,
)
from .imu import ImuFeedback, ImuReader, SimulatedImuReader
from .pid import PidController, PidDebug, PidGains
from .visual import VisualFeedback, VisualTarget

__all__ = [
    "BaseFeedbackSource",
    "DEFAULT_BEARING_GAINS",
    "DEFAULT_RANGE_GAINS",
    "DriveCommand",
    "EncoderGeometry",
    "FeedbackBus",
    "FeedbackSource",
    "FollowState",
    "FollowTuning",
    "ImuFeedback",
    "ImuReader",
    "MotionEstimate",
    "PersonFollower",
    "PidController",
    "PidDebug",
    "PidGains",
    "SimulatedImuReader",
    "VisualFeedback",
    "VisualTarget",
    "WheelEncoderFeedback",
]
