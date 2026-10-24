"""
Internal laptop display backlight backend using Linux sysfs and brightnessctl.
"""

from __future__ import annotations

import glob
import logging
import os
import subprocess
import time
from typing import List, Optional

from ..core.models import OperationResult
from ..core.validation import clamp_brightness

logger = logging.getLogger(__name__)


class SysfsBacklightBackend:
    """Controls laptop internal screen backlight using sysfs and brightnessctl."""

    def __init__(self, sysfs_path: Optional[str] = None, output_name: Optional[str] = None):
        self.sysfs_path = sysfs_path or self._find_default_backlight()
        self.output_name = output_name
        self.max_brightness = 100
        self._last_val = 100

        if self.sysfs_path and os.path.isdir(self.sysfs_path):
            try:
                with open(os.path.join(self.sysfs_path, "max_brightness")) as f:
                    self.max_brightness = max(1, int(f.read().strip()))
            except Exception as e:
                logger.warning(f"Could not read max_brightness from {self.sysfs_path}: {e}")

    @staticmethod
    def _find_default_backlight() -> Optional[str]:
        candidates = glob.glob("/sys/class/backlight/*")
        if not candidates:
            return None
        # Prefer intel_backlight, amdgpu_bl*, then acpi_video*
        for pref in ("intel_backlight", "amdgpu_bl", "nvidia_wmi_ec_backlight", "acpi_video"):
            for c in candidates:
                if pref in os.path.basename(c):
                    return c
        return candidates[0]

    @staticmethod
    def list_backlight_devices() -> List[str]:
        return glob.glob("/sys/class/backlight/*")

    def get_brightness(self) -> Optional[int]:
        """Read current brightness as a percentage (1-100)."""
        # 1. Direct sysfs read
        if self.sysfs_path and os.path.isdir(self.sysfs_path):
            try:
                with open(os.path.join(self.sysfs_path, "brightness")) as f:
                    cur = int(f.read().strip())
                val = clamp_brightness(round((cur / self.max_brightness) * 100))
                self._last_val = max(1, val)
                return self._last_val
            except Exception as e:
                logger.debug(f"Sysfs read error: {e}")

        # 2. brightnessctl fallback
        try:
            res = subprocess.run(["brightnessctl", "-m"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().splitlines()[0].split(",")
                if len(parts) >= 4 and "%" in parts[3]:
                    val = int(parts[3].replace("%", ""))
                    self._last_val = max(1, clamp_brightness(val))
                    return self._last_val
        except Exception:
            pass

        return self._last_val

    def set_brightness(self, percentage: int) -> OperationResult:
        """Set backlight brightness percentage (1-100)."""
        t0 = time.time()
        val = max(1, clamp_brightness(percentage))
        self._last_val = val

        # 1. Primary: brightnessctl (handles permissions transparently via udev / setuid)
        try:
            res = subprocess.run(
                ["brightnessctl", "set", f"{val}%"],
                capture_output=True, text=True, timeout=4
            )
            if res.returncode == 0:
                return OperationResult(
                    success=True,
                    verified=True,
                    requested_value=val,
                    actual_value=val,
                    latency_ms=(time.time() - t0) * 1000.0,
                )
        except Exception:
            pass

        # 2. Direct sysfs write (works if user is in video/input group or root udev rules set)
        if self.sysfs_path and os.path.isdir(self.sysfs_path):
            try:
                target_raw = int(round((val / 100.0) * self.max_brightness))
                with open(os.path.join(self.sysfs_path, "brightness"), "w") as f:
                    f.write(str(target_raw))
                return OperationResult(
                    success=True,
                    verified=True,
                    requested_value=val,
                    actual_value=val,
                    latency_ms=(time.time() - t0) * 1000.0,
                )
            except PermissionError:
                logger.debug("Permission denied for direct sysfs brightness write")
            except Exception as e:
                logger.warning(f"Sysfs write failed: {e}")

        # 3. Software XRandR brightness fallback
        if self.output_name:
            try:
                frac = round(val / 100.0, 2)
                res = subprocess.run(
                    ["xrandr", "--output", self.output_name, "--brightness", str(frac)],
                    capture_output=True, text=True, timeout=4
                )
                if res.returncode == 0:
                    return OperationResult(
                        success=True,
                        verified=False,
                        requested_value=val,
                        actual_value=val,
                        latency_ms=(time.time() - t0) * 1000.0,
                    )
            except Exception as e:
                logger.error(f"XRandR brightness fallback failed: {e}")

        return OperationResult(
            success=False,
            verified=False,
            requested_value=val,
            error_message="All backlight write methods failed",
            latency_ms=(time.time() - t0) * 1000.0,
        )


# Global default instance
backlight_backend = SysfsBacklightBackend()
