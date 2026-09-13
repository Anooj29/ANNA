"""Shared fixtures.

Every test runs against the simulated GPIO backend, so the whole suite runs
on any machine with no Raspberry Pi, no camera and no models.
"""

from __future__ import annotations

import pytest

from anna_robot.hardware import gpio as gpio_module


@pytest.fixture(autouse=True)
def simulated_gpio():
    """Give each test a clean simulated GPIO backend."""
    backend = gpio_module.use_simulation()
    backend.setmode(backend.BCM)
    yield backend
    gpio_module.reset_backend()
