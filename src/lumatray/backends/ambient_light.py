"""
Ambient light sensor backend using Linux Industrial I/O (IIO) subsystem.
"""

from __future__ import annotations

import glob
import logging
import math
import os
from typing import Optional

from ..core.validation import clamp_brightness

logger = logging.getLogger(__name__)


class AmbientLightBackend:
    """Reads ambient illuminance from Linux IIO sensors."""

    def __init__(self):
        self._sensor_path: Optional[str] = self._detect_sensor()

    def _detect_sensor(self) -> Optional[str]:
        # Search /sys/bus/iio/devices for illuminance input files
        for device_dir in glob.glob("/sys/bus/iio/devices/iio:device*"):
            for candidate in ("in_illuminance_input", "in_illuminance_raw", "illuminance0_input"):
                path = os.path.join(device_dir, candidate)
                if os.path.exists(path):
                    return path
        return None

    def is_available(self) -> bool:
        """Return True if an ambient light sensor is physically present and accessible."""
        return self._sensor_path is not None and os.access(self._sensor_path, os.R_OK)

    def get_lux(self) -> Optional[float]:
        """Read current illuminance in Lux."""
        if not self._sensor_path:
            return None
        try:
            with open(self._sensor_path, "r") as f:
                raw = float(f.read().strip())
            # Check for scale factor file if present
            scale_path = os.path.join(os.path.dirname(self._sensor_path), "in_illuminance_scale")
            scale = 1.0
            if os.path.exists(scale_path):
                try:
                    with open(scale_path, "r") as sf:
                        scale = float(sf.read().strip())
                except Exception:
                    pass
            return max(0.0, raw * scale)
        except Exception as e:
            logger.debug(f"Failed to read ambient light sensor: {e}")
            return None

    def compute_target_brightness(
        self, lux: float, min_brightness: int = 15, max_brightness: int = 100
    ) -> int:
        """Compute recommended monitor brightness using a logarithmic perceptual response curve.
        
        Typical lux values:
        - 0-20 lux: Dark bedroom -> min_brightness
        - 50-150 lux: Dim living room -> ~40-55%
        - 300-500 lux: Bright office -> ~75-85%
        - 1000+ lux: Direct sunlight -> max_brightness
        """
        lux = max(0.1, lux)
        # Logarithmic mapping from 1 lux (0%) to 1000 lux (100%)
        log_min = math.log10(1.0)      # 0.0
        log_max = math.log10(1000.0)   # 3.0
        current_log = min(log_max, max(log_min, math.log10(lux)))
        factor = (current_log - log_min) / (log_max - log_min)

        target = min_brightness + factor * (max_brightness - min_brightness)
        return clamp_brightness(target)


# Global singleton instance
ambient_backend = AmbientLightBackend()
