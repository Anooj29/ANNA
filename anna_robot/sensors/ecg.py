"""Single-lead ECG acquisition via an ADS1115 ADC.

This performs a rough rhythm-regularity estimate from peak-to-peak timing.
It is NOT a diagnostic-quality ECG reading and must never be presented to a
patient as a medical diagnosis.

Changed from the original: the I2C bus and ADC are opened **lazily**, on the
first reading, rather than in the constructor. Opening them eagerly meant a
missing or unpowered ADC took the whole robot down at startup, even on a run
that was never going to record an ECG.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import numpy as np

from ..hardware.gpio import get_gpio

logger = logging.getLogger(__name__)


class EcgSensor:
    LEADS_OFF = "Leads not attached - check electrodes"
    WEAK_SIGNAL = "Weak ECG signal - check electrode placement"
    UNAVAILABLE = "ECG hardware unavailable"

    def __init__(
        self,
        lo_plus_pin: int,
        lo_minus_pin: int,
        sample_count: int = 500,
        sample_interval_s: float = 0.01,
        adc_gain: int = 1,
        adc_channel: int = 0,
    ) -> None:
        self._gpio = get_gpio()
        self._gpio.setup(lo_plus_pin, self._gpio.IN, pull_up_down=self._gpio.PUD_DOWN)
        self._gpio.setup(lo_minus_pin, self._gpio.IN, pull_up_down=self._gpio.PUD_DOWN)
        self._lo_plus = lo_plus_pin
        self._lo_minus = lo_minus_pin
        self._sample_count = max(int(sample_count), 10)
        self._sample_interval = float(sample_interval_s)
        self._adc_gain = int(adc_gain)
        self._adc_channel = int(adc_channel)
        self._channel = None
        self._adc_error: Optional[str] = None

    # -- hardware ---------------------------------------------------------
    def _ensure_adc(self) -> bool:
        """Open the ADS1115 on first use. Returns False if unavailable."""
        if self._channel is not None:
            return True
        if self._adc_error is not None:
            return False
        try:
            import adafruit_ads1x15.ads1115 as ADS  # type: ignore[import-not-found]
            import board  # type: ignore[import-not-found]
            import busio  # type: ignore[import-not-found]
            from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore[import-not-found]

            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c)
            ads.gain = self._adc_gain
            self._channel = AnalogIn(ads, self._adc_channel)
            logger.info("ECG front-end ready on ADS1115 channel %d.", self._adc_channel)
            return True
        except Exception as exc:
            self._adc_error = str(exc)
            logger.warning("ECG ADC unavailable (%s); ECG readings will report as unavailable.", exc)
            return False

    @property
    def leads_attached(self) -> bool:
        """AD8232 pulls LO+ / LO- high when an electrode falls off."""
        return not (self._gpio.input(self._lo_plus) == 1 or self._gpio.input(self._lo_minus) == 1)

    # -- acquisition ------------------------------------------------------
    def record_and_analyze(self) -> str:
        """Record a short trace and describe its rhythm regularity."""
        try:
            if not self.leads_attached:
                return self.LEADS_OFF
            if not self._ensure_adc():
                return self.UNAVAILABLE

            duration_s = self._sample_count * self._sample_interval
            logger.info("Recording ECG for %.0f seconds...", duration_s)
            samples = self._collect_samples()
            return self.analyze(np.asarray(samples, dtype=np.float32))
        except Exception as exc:
            logger.exception("ECG acquisition failed.")
            return f"Error: {exc}"

    def _collect_samples(self) -> List[int]:
        """Sample the ADC on a fixed schedule.

        Scheduling against a monotonic deadline keeps the sample rate
        honest; the original ``sleep(interval)`` loop drifted by however
        long each I2C read took, which biases the rhythm estimate.
        """
        samples: List[int] = []
        next_sample_at = time.monotonic()
        for _ in range(self._sample_count):
            samples.append(self._channel.value)
            next_sample_at += self._sample_interval
            remaining = next_sample_at - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
        return samples

    def analyze(self, signal: np.ndarray) -> str:
        """Classify rhythm regularity from peak-to-peak interval spread."""
        if signal.size < 10:
            return self.WEAK_SIGNAL
        signal = signal - float(np.mean(signal))
        threshold = float(np.std(signal)) * 0.6
        if threshold <= 0.0:
            return self.WEAK_SIGNAL

        min_separation = max(int(0.25 / self._sample_interval), 1)  # 250 ms refractory
        peaks: List[int] = []
        for index in range(1, signal.size - 1):
            value = signal[index]
            if value > threshold and value > signal[index - 1] and value >= signal[index + 1]:
                if not peaks or (index - peaks[-1]) > min_separation:
                    peaks.append(index)

        if len(peaks) < 3:
            return self.WEAK_SIGNAL

        intervals = np.diff(peaks)
        mean_interval = float(np.mean(intervals))
        if mean_interval <= 0:
            return self.WEAK_SIGNAL
        variability = float(np.std(intervals)) / mean_interval
        bpm = 60.0 / (mean_interval * self._sample_interval)

        if variability < 0.15:
            rhythm = "Normal Sinus Rhythm"
        elif variability < 0.30:
            rhythm = "Slightly Irregular"
        else:
            rhythm = "Irregular - consult doctor"
        return f"{rhythm} (approx {bpm:.0f} BPM)"
