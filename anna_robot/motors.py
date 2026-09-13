"""Differential-drive motor control."""

from __future__ import annotations

import logging

import RPi.GPIO as GPIO

logger = logging.getLogger(__name__)


class MotorController:
    """Note: this hardware only drives forward - steering is done purely by
    biasing the PWM duty cycle between the two wheels, matching the
    original robot's wiring. There is no reverse gear."""

    def __init__(self, left_dir: int, left_pwm: int, right_dir: int, right_pwm: int, pwm_freq_hz: int = 1000) -> None:
        GPIO.setup(left_dir, GPIO.OUT)
        GPIO.setup(right_dir, GPIO.OUT)
        GPIO.setup(left_pwm, GPIO.OUT)
        GPIO.setup(right_pwm, GPIO.OUT)
        self._left_dir = left_dir
        self._right_dir = right_dir
        self._left_motor = GPIO.PWM(left_pwm, pwm_freq_hz)
        self._right_motor = GPIO.PWM(right_pwm, pwm_freq_hz)
        self._left_motor.start(0)
        self._right_motor.start(0)

    def forward(self) -> None:
        GPIO.output(self._left_dir, 0)
        GPIO.output(self._right_dir, 0)
        self._left_motor.ChangeDutyCycle(50)
        self._right_motor.ChangeDutyCycle(50)
        logger.debug("Motor: forward")

    def turn_left(self) -> None:
        GPIO.output(self._left_dir, 0)
        GPIO.output(self._right_dir, 0)
        self._left_motor.ChangeDutyCycle(25)
        self._right_motor.ChangeDutyCycle(50)
        logger.debug("Motor: left")

    def turn_right(self) -> None:
        GPIO.output(self._left_dir, 0)
        GPIO.output(self._right_dir, 0)
        self._left_motor.ChangeDutyCycle(50)
        self._right_motor.ChangeDutyCycle(25)
        logger.debug("Motor: right")

    def stop(self) -> None:
        self._left_motor.ChangeDutyCycle(0)
        self._right_motor.ChangeDutyCycle(0)
        GPIO.output(self._left_dir, 0)
        GPIO.output(self._right_dir, 0)
        logger.debug("Motor: stop")
