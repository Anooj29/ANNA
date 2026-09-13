"""DS18B20 1-Wire body temperature probe."""

from __future__ import annotations

import glob
import logging
import os
import time

logger = logging.getLogger(__name__)


class TemperatureSensor:
    def __init__(self, w1_base_dir: str = "/sys/bus/w1/devices/", retries: int = 5, retry_delay_s: float = 0.2) -> None:
        self._base_dir = w1_base_dir
        self._retries = retries
        self._retry_delay = retry_delay_s

    def read_celsius(self) -> str:
        device_folders = glob.glob(self._base_dir + "28*")
        if not device_folders:
            return "Sensor not found"

        device_file = os.path.join(device_folders[0], "w1_slave")

        for _ in range(self._retries):
            try:
                with open(device_file, "r") as handle:
                    lines = handle.readlines()
            except OSError:
                logger.exception("Could not read the temperature sensor file.")
                return "Temp read error"

            if lines and lines[0].strip().endswith("YES"):
                temp_pos = lines[1].find("t=")
                if temp_pos != -1:
                    temp_c = float(lines[1][temp_pos + 2:]) / 1000.0
                    return f"{round(temp_c, 2)} C"

            time.sleep(self._retry_delay)

        return "Temp read error"
