"""DS18B20 1-Wire body temperature probe."""

from __future__ import annotations

import glob
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


class TemperatureSensor:
    """Reads the 1-Wire probe, retrying until the CRC line reads 'YES'."""

    NOT_FOUND = "Sensor not found"
    READ_ERROR = "Temp read error"

    def __init__(
        self,
        w1_base_dir: str = "/sys/bus/w1/devices/",
        retries: int = 5,
        retry_delay_s: float = 0.2,
    ) -> None:
        self._base_dir = w1_base_dir
        self._retries = max(int(retries), 1)
        self._retry_delay = float(retry_delay_s)
        self.last_celsius: Optional[float] = None

    def _device_file(self) -> Optional[str]:
        folders = glob.glob(os.path.join(self._base_dir, "28*"))
        return os.path.join(folders[0], "w1_slave") if folders else None

    def read_celsius(self) -> str:
        """Return a display string such as ``"36.7 C"``, or an error string."""
        value = self.read_value()
        return self.NOT_FOUND if value is None and self._device_file() is None else (
            self.READ_ERROR if value is None else f"{round(value, 2)} C"
        )

    def read_value(self) -> Optional[float]:
        """The reading in degrees Celsius, or None if it could not be read."""
        device_file = self._device_file()
        if device_file is None:
            logger.warning("No DS18B20 device found under '%s'.", self._base_dir)
            return None

        for _ in range(self._retries):
            try:
                with open(device_file, "r") as handle:
                    lines = handle.readlines()
            except OSError:
                logger.exception("Could not read the temperature sensor file.")
                return None

            if len(lines) >= 2 and lines[0].strip().endswith("YES"):
                position = lines[1].find("t=")
                if position != -1:
                    try:
                        # A partially written sysfs line yields junk here; it
                        # used to raise ValueError and take the robot down.
                        celsius = float(lines[1][position + 2:].strip()) / 1000.0
                    except ValueError:
                        logger.warning("Malformed temperature reading: %r", lines[1].strip())
                    else:
                        if -55.0 <= celsius <= 125.0:  # the DS18B20's own range
                            self.last_celsius = celsius
                            return celsius
                        logger.warning("Temperature %.2f C is outside the sensor's range; ignoring it.", celsius)
            time.sleep(self._retry_delay)

        logger.warning("Temperature sensor did not return a valid reading after %d attempts.", self._retries)
        return None
