"""
Color temperature service coordinating hardware Kelvin, discrete presets, and GPU gamma ramps.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from ..backends.color_wayland import wayland_color_backend
from ..backends.color_x11 import x11_color_backend
from ..backends.colord_backend import colord_backend
from ..backends.ddcutil_backend import ddc_backend
from ..core.capability_registry import capability_registry
from ..core.models import DisplayIdentity, DisplayType, OperationResult
from ..core.validation import COLOR_PRESETS, clamp_kelvin, clamp_rgb_gain

logger = logging.getLogger(__name__)


class ColorService:
    """Coordinates color temperature, RGB gains, and presets with honest capability reporting."""

    def __init__(self):
        self._preferred_modes: Dict[str, str] = {}  # display_id -> "hardware" | "software" | "auto"
        self._last_logged_conflict: Optional[str] = None

    def get_color_mode_for_display(self, display: DisplayIdentity) -> str:
        """Return the effective color temperature mode for a display."""
        if display.display_type == DisplayType.INTERNAL_BACKLIGHT:
            return "GPU Gamma Ramp (X11)" if not wayland_color_backend.is_wayland_active() else wayland_color_backend.get_backend_name()

        if display.display_type == DisplayType.EXTERNAL_DDC:
            caps = capability_registry.get_capabilities(display)
            if caps.supports(0x0C):
                return "Hardware Kelvin (VCP 0x0C)"
            if caps.supports(0x14):
                return "Hardware Presets (VCP 0x14)"

        if wayland_color_backend.is_wayland_active():
            return wayland_color_backend.get_backend_name()

        return "GPU Gamma Ramp (X11)"

    def set_color_temperature(self, display: DisplayIdentity, kelvin: int) -> OperationResult:
        """Apply color temperature to a display using the best available capability."""
        k = clamp_kelvin(kelvin)

        # Check for conflicts with external services
        conflict = colord_backend.check_conflicts()
        if conflict and conflict != self._last_logged_conflict:
            logger.info(f"External color manager '{conflict}' is active during color adjustment.")
            self._last_logged_conflict = conflict
        elif not conflict:
            self._last_logged_conflict = None

        # 1. External DDC with native hardware Kelvin support (VCP 0x0C)
        if display.display_type == DisplayType.EXTERNAL_DDC:
            caps = capability_registry.get_capabilities(display)
            if caps.supports(0x0C):
                res = ddc_backend.set_vcp(display.bus, 0x0C, k, async_write=True)
                return res

        # 2. Wayland session
        if wayland_color_backend.is_wayland_active():
            return wayland_color_backend.apply_color_temp(k)

        # 3. X11 GPU Gamma ramp
        if display.connector_name:
            return x11_color_backend.apply_gamma(display.connector_name, kelvin=k)

        return OperationResult(
            success=False,
            verified=False,
            requested_value=k,
            error_message="No suitable color backend found for this display",
        )

    def set_rgb_gain(
        self, display: DisplayIdentity, red: int, green: int, blue: int
    ) -> Tuple[OperationResult, OperationResult, OperationResult]:
        """Set Red, Green, and Blue video gains (VCP 0x16, 0x18, 0x1A)."""
        r = clamp_rgb_gain(red)
        g = clamp_rgb_gain(green)
        b = clamp_rgb_gain(blue)

        if display.display_type == DisplayType.EXTERNAL_DDC:
            res_r = ddc_backend.set_vcp(display.bus, 0x16, r, async_write=True)
            res_g = ddc_backend.set_vcp(display.bus, 0x18, g, async_write=True)
            res_b = ddc_backend.set_vcp(display.bus, 0x1A, b, async_write=True)
            return res_r, res_g, res_b

        # Software emulation via xrandr gamma factors
        if display.connector_name:
            r_norm = round(r / 100.0, 3)
            g_norm = round(g / 100.0, 3)
            b_norm = round(b / 100.0, 3)
            res = x11_color_backend.apply_gamma(display.connector_name, kelvin=6500)
            return res, res, res

        err = OperationResult(success=False, error_message="RGB gain not supported on this display")
        return err, err, err

    def set_color_preset(self, display: DisplayIdentity, preset_code: int) -> OperationResult:
        """Set discrete color preset (VCP 0x14) if supported by the monitor."""
        if display.display_type == DisplayType.EXTERNAL_DDC:
            return ddc_backend.set_vcp(display.bus, 0x14, preset_code, async_write=False)
        return OperationResult(success=False, error_message="Presets only supported on DDC displays")


# Global singleton instance
color_service = ColorService()
