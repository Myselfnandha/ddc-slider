"""
X11 gamma and color temperature backend using xrandr and Tanner-Helland algorithm.
"""

from __future__ import annotations

import logging
import math
import subprocess
import time
from typing import Optional, Tuple

from ..core.models import OperationResult
from ..core.validation import clamp_contrast, clamp_kelvin

logger = logging.getLogger(__name__)


def kelvin_to_rgb(kelvin: int) -> Tuple[float, float, float]:
    """Convert color temperature in Kelvin (1000K-10000K) to normalized RGB multipliers (0.0 - 1.0).
    Neutral daylight (6500K) maps to (1.0, 1.0, 1.0).
    Algorithm: Tanner Helland.
    """
    kelvin = clamp_kelvin(kelvin)
    temp = kelvin / 100.0

    # Red
    if temp <= 66:
        r = 255.0
    else:
        r = 329.698727446 * ((temp - 60.0) ** -0.1332047592)
    r = max(0.0, min(255.0, r))

    # Green
    if temp <= 66:
        g = 99.4708025861 * math.log(max(1.0, temp)) - 161.1195681661
    else:
        g = 288.1221695283 * ((temp - 60.0) ** -0.0755148492)
    g = max(0.0, min(255.0, g))

    # Blue
    if temp >= 66:
        b = 255.0
    elif temp <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(max(1.0, temp - 10.0)) - 305.0447927307
    b = max(0.0, min(255.0, b))

    # Normalized relative to standard D65 6500K
    r_factor = max(0.0, min(1.0, r / 255.0))
    g_factor = max(0.0, min(1.0, g / 254.18))
    b_factor = max(0.0, min(1.0, b / 249.98))
    return round(r_factor, 3), round(g_factor, 3), round(b_factor, 3)


class X11ColorBackend:
    """Manages color temperature and software contrast gamma ramps via xrandr."""

    def __init__(self):
        self._last_gamma: dict[str, tuple[float, float, float]] = {}

    def apply_gamma(
        self,
        output_name: str,
        kelvin: int = 6500,
        contrast: int = 50,
        is_software_contrast: bool = False,
    ) -> OperationResult:
        """Apply color temperature and contrast to an X11 display output."""
        t0 = time.time()
        r_temp, g_temp, b_temp = kelvin_to_rgb(kelvin)

        if is_software_contrast:
            # Contrast scaling: 50% = factor 1.0 (0% = 0.5, 100% = 1.5)
            c = clamp_contrast(contrast)
            contrast_factor = 0.5 + (c / 100.0)
            r = max(0.1, min(3.0, r_temp * contrast_factor))
            g = max(0.1, min(3.0, g_temp * contrast_factor))
            b = max(0.1, min(3.0, b_temp * contrast_factor))
        else:
            r, g, b = r_temp, g_temp, b_temp

        gamma_tuple = (round(r, 3), round(g, 3), round(b, 3))
        if self._last_gamma.get(output_name) == gamma_tuple:
            return OperationResult(
                success=True,
                verified=True,
                requested_value=kelvin,
                actual_value=gamma_tuple,
                latency_ms=(time.time() - t0) * 1000.0,
            )

        try:
            cmd = [
                "xrandr",
                "--output", output_name,
                "--gamma", f"{r:.3f}:{g:.3f}:{b:.3f}",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
            if res.returncode == 0:
                self._last_gamma[output_name] = gamma_tuple
                return OperationResult(
                    success=True,
                    verified=True,
                    requested_value=kelvin,
                    actual_value=gamma_tuple,
                    latency_ms=(time.time() - t0) * 1000.0,
                )
            else:
                return OperationResult(
                    success=False,
                    verified=False,
                    requested_value=kelvin,
                    error_message=res.stderr.strip() or "xrandr gamma failed",
                    latency_ms=(time.time() - t0) * 1000.0,
                )
        except Exception as e:
            return OperationResult(
                success=False,
                verified=False,
                requested_value=kelvin,
                error_message=str(e),
                latency_ms=(time.time() - t0) * 1000.0,
            )

    def reset_gamma(self, output_name: str) -> OperationResult:
        """Reset gamma ramp for an output to neutral 1.0:1.0:1.0."""
        return self.apply_gamma(output_name, kelvin=6500, contrast=50, is_software_contrast=False)


# Global singleton instance
x11_color_backend = X11ColorBackend()
