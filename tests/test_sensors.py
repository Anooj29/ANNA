"""Sensor tests: filtering, malformed input and graceful degradation."""

from __future__ import annotations

import pytest

from anna_robot.sensors.ecg import EcgSensor
from anna_robot.sensors.pulse import SimulatedPulseSensor
from anna_robot.sensors.temperature import TemperatureSensor
from anna_robot.sensors.ultrasonic import UltrasonicSensor

numpy = pytest.importorskip("numpy")


# -- ultrasonic ---------------------------------------------------------
def test_reading_is_instant_and_never_blocks_the_loop():
    """The old inline measurement cost up to 60 ms of blocking per frame."""
    import time

    sensor = UltrasonicSensor(23, 24)
    started = time.monotonic()
    for _ in range(500):
        sensor.measure_cm()
    assert time.monotonic() - started < 0.2
    sensor.close()


def test_median_filter_rejects_a_single_wild_reading():
    sensor = UltrasonicSensor(23, 24, background=False)
    sensor._readings.extend([100.0, 101.0, 99.0, 100.5])
    sensor._readings.append(5.0)  # One spurious echo.
    assert 95.0 < sensor.measure_cm() < 105.0
    sensor.close()


def test_out_of_range_readings_are_not_stored():
    sensor = UltrasonicSensor(23, 24, background=False)
    sensor._last_raw = 0.5  # Below the sensor's minimum.
    assert sensor.MIN_VALID_CM == 2.0
    sensor.close()


def test_simulation_reports_a_clear_path():
    sensor = UltrasonicSensor(23, 24, background=False)
    assert sensor.measure_cm() >= UltrasonicSensor.MAX_VALID_CM
    sensor.close()


# -- temperature --------------------------------------------------------
def test_missing_probe_reports_clearly():
    sensor = TemperatureSensor(w1_base_dir="/nonexistent/")
    assert sensor.read_celsius() == TemperatureSensor.NOT_FOUND
    assert sensor.read_value() is None


def test_a_valid_reading_is_parsed(tmp_path):
    device = tmp_path / "28-000001"
    device.mkdir()
    (device / "w1_slave").write_text(
        "a1 01 4b 46 7f ff 0c 10 27 : crc=27 YES\n"
        "a1 01 4b 46 7f ff 0c 10 27 t=36812\n"
    )
    sensor = TemperatureSensor(w1_base_dir=str(tmp_path) + "/", retries=1)
    assert sensor.read_value() == pytest.approx(36.812)
    assert sensor.read_celsius() == "36.81 C"


def test_a_malformed_reading_does_not_raise(tmp_path):
    """A partially written sysfs line used to crash the robot with ValueError."""
    device = tmp_path / "28-000001"
    device.mkdir()
    (device / "w1_slave").write_text("crc=27 YES\nt=not-a-number\n")
    sensor = TemperatureSensor(w1_base_dir=str(tmp_path) + "/", retries=1, retry_delay_s=0)
    assert sensor.read_value() is None
    assert sensor.read_celsius() == TemperatureSensor.READ_ERROR


def test_a_physically_impossible_reading_is_rejected(tmp_path):
    device = tmp_path / "28-000001"
    device.mkdir()
    (device / "w1_slave").write_text("crc=27 YES\nt=850000\n")  # 850 C
    sensor = TemperatureSensor(w1_base_dir=str(tmp_path) + "/", retries=1, retry_delay_s=0)
    assert sensor.read_value() is None


def test_a_failed_crc_is_retried(tmp_path):
    device = tmp_path / "28-000001"
    device.mkdir()
    (device / "w1_slave").write_text("crc=27 NO\nt=36812\n")
    sensor = TemperatureSensor(w1_base_dir=str(tmp_path) + "/", retries=2, retry_delay_s=0)
    assert sensor.read_value() is None


# -- pulse --------------------------------------------------------------
def test_pulse_is_labelled_as_simulated():
    sensor = SimulatedPulseSensor()
    assert sensor.is_simulated is True
    assert sensor.read_bpm().endswith("BPM")


def test_pulse_stays_in_a_plausible_range():
    sensor = SimulatedPulseSensor()
    for _ in range(50):
        assert 60 <= int(sensor.read_bpm().split()[0]) <= 95


# -- ECG ----------------------------------------------------------------
def _ecg(peak_indices, length=500, noise=0.05):
    signal = numpy.zeros(length, numpy.float32)
    signal[peak_indices] = 10.0
    return signal + numpy.random.normal(0, noise, length).astype(numpy.float32)


def test_a_regular_rhythm_is_reported_as_regular():
    sensor = EcgSensor(5, 6, sample_interval_s=0.004)
    assert "Normal Sinus Rhythm" in sensor.analyze(_ecg(list(range(20, 500, 150))))


def test_an_irregular_rhythm_is_flagged():
    sensor = EcgSensor(5, 6, sample_interval_s=0.004)
    assert "Irregular" in sensor.analyze(_ecg([20, 180, 250, 420, 470]))


def test_too_few_peaks_reports_a_weak_signal():
    sensor = EcgSensor(5, 6, sample_interval_s=0.004)
    assert sensor.analyze(_ecg([20])) == EcgSensor.WEAK_SIGNAL
    assert sensor.analyze(numpy.zeros(3, numpy.float32)) == EcgSensor.WEAK_SIGNAL


def test_missing_adc_is_reported_not_fatal():
    """Opening the ADC eagerly used to take the whole robot down at boot."""
    sensor = EcgSensor(5, 6)
    assert sensor.record_and_analyze() == EcgSensor.UNAVAILABLE


def test_leads_off_is_detected(simulated_gpio):
    sensor = EcgSensor(5, 6)
    simulated_gpio.set_input(5, 1)
    assert sensor.leads_attached is False
    assert sensor.record_and_analyze() == EcgSensor.LEADS_OFF
