"""Single-lead ECG acquisition via an ADS1115 ADC.

This performs a rough rhythm-regularity estimate from peak-to-peak timing.
It is NOT a diagnostic-quality ECG reading and must never be presented to a
patient as a medical diagnosis.
"""

from __future__ import annotations

import logging
import time
from typing import List

import numpy as np
import RPi.GPIO as GPIO
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

logger = logging.getLogger(__name__)


class EcgSensor:
    def __init__(self, lo_plus_pin: int, lo_minus_pin: int, sample_count: int = 500, sample_interval_s: float = 0.01) -> None:
        GPIO.setup(lo_plus_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(lo_minus_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        self._lo_plus = lo_plus_pin
        self._lo_minus = lo_minus_pin
        self._sample_count = sample_count
        self._sample_interval = sample_interval_s

        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        ads.gain = 1
        self._channel = AnalogIn(ads, 0)

    def record_and_analyze(self) -> str:
        try:
            if GPIO.input(self._lo_plus) == 1 or GPIO.input(self._lo_minus) == 1:
                return "Leads not attached - check electrodes"

            logger.info("Recording ECG for %.0f seconds...", self._sample_count * self._sample_interval)
            samples = []
            for _ in range(self._sample_count):
                samples.append(self._channel.value)
                time.sleep(self._sample_interval)

            signal = np.array(samples, dtype=np.float32)
            signal -= np.mean(signal)

            threshold = np.std(signal) * 0.6
            peaks: List[int] = []
            for i in range(1, len(signal) - 1):
                if signal[i] > threshold and signal[i] > signal[i - 1] and signal[i] > signal[i + 1]:
                    if not peaks or (i - peaks[-1]) > 30:
                        peaks.append(i)

            if len(peaks) < 3:
                return "Weak ECG signal - check electrode placement"

            intervals = np.diff(peaks)
            variability = np.std(intervals) / np.mean(intervals)

            if variability < 0.15:
                return "Normal Sinus Rhythm"
            if variability < 0.30:
                return "Slightly Irregular"
            return "Irregular - consult doctor"

        except Exception as exc:
            logger.exception("ECG acquisition failed.")
            return f"Error: {exc}"
