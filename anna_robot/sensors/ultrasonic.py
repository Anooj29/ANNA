"""HC-SR04-style ultrasonic distance sensor."""

from __future__ import annotations

import time

import RPi.GPIO as GPIO


class UltrasonicSensor:
    NO_ECHO_DISTANCE_CM = 999.0

    def __init__(self, trig_pin: int, echo_pin: int, pulse_timeout_s: float = 0.05) -> None:
        GPIO.setup(trig_pin, GPIO.OUT)
        GPIO.setup(echo_pin, GPIO.IN)
        self._trig = trig_pin
        self._echo = echo_pin
        self._timeout = pulse_timeout_s

    def measure_cm(self) -> float:
        GPIO.output(self._trig, False)
        time.sleep(0.02)
        GPIO.output(self._trig, True)
        time.sleep(0.00001)
        GPIO.output(self._trig, False)

        start_wait = time.time()
        while GPIO.input(self._echo) == 0:
            if time.time() - start_wait > self._timeout:
                return self.NO_ECHO_DISTANCE_CM
        pulse_start = time.time()

        while GPIO.input(self._echo) == 1:
            if time.time() - pulse_start > self._timeout:
                return self.NO_ECHO_DISTANCE_CM
        pulse_end = time.time()

        return round((pulse_end - pulse_start) * 17150, 2)
