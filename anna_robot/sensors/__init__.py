"""Hardware sensor wrappers (ultrasonic, temperature, pulse, ECG).

Each one degrades to a clear, non-fatal error string when its hardware is
missing, so a single unplugged sensor can never stop the robot.
"""

from .ecg import EcgSensor
from .pulse import SimulatedPulseSensor
from .temperature import TemperatureSensor
from .ultrasonic import UltrasonicSensor

__all__ = ["EcgSensor", "SimulatedPulseSensor", "TemperatureSensor", "UltrasonicSensor"]
