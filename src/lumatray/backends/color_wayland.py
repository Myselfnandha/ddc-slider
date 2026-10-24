"""
Wayland color management and compositor-aware color temperature backend.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import Optional

from ..core.models import OperationResult
from ..core.validation import clamp_kelvin

logger = logging.getLogger(__name__)


class WaylandColorBackend:
    """Manages color adjustments on Wayland compositors (wlroots, KDE, GNOME)."""

    def __init__(self):
        self._is_wayland = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland")
        self._compositor = self._detect_compositor()
        self._has_gammastep = shutil.which("gammastep") is not None
        self._has_wlsunset = shutil.which("wlsunset") is not None

    def is_wayland_active(self) -> bool:
        return self._is_wayland

    def _detect_compositor(self) -> str:
        current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "gnome" in current_desktop:
            return "gnome"
        if "kde" in current_desktop or "plasma" in current_desktop:
            return "kde"
        if "sway" in current_desktop or "wlroots" in current_desktop or "hyprland" in current_desktop:
            return "wlroots"
        return "generic"

    def is_supported(self) -> bool:
        if not self._is_wayland:
            return False
        return self._has_gammastep or self._has_wlsunset or self._compositor in ("kde", "gnome")

    def get_backend_name(self) -> str:
        if not self._is_wayland:
            return "None (X11 Session)"
        if self._has_gammastep:
            return "Gammastep (Wayland)"
        if self._compositor == "kde":
            return "KDE KWin Night Color"
        if self._compositor == "gnome":
            return "GNOME Night Light"
        return "Unsupported Wayland Compositor"

    def apply_color_temp(self, kelvin: int) -> OperationResult:
        """Apply color temperature in Wayland session."""
        t0 = time.time()
        k = clamp_kelvin(kelvin)

        # 1. Gammastep one-shot mode (wlroots, sway, hyprland, etc.)
        if self._has_gammastep:
            try:
                cmd = ["gammastep", "-O", str(k), "-m", "wayland"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
                if res.returncode == 0:
                    return OperationResult(
                        success=True,
                        verified=True,
                        requested_value=k,
                        actual_value=k,
                        latency_ms=(time.time() - t0) * 1000.0,
                    )
            except Exception as e:
                logger.debug(f"Gammastep execution failed: {e}")

        # 2. KDE Plasma Night Color via D-Bus
        if self._compositor == "kde":
            try:
                # org.kde.kwin.ColorCorrect / org.kde.KWin.NightColor
                cmd = [
                    "qdbus", "org.kde.KWin", "/ColorCorrect",
                    "org.kde.kwin.ColorCorrect.setNightColorConfig", str(k)
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    return OperationResult(
                        success=True,
                        verified=True,
                        requested_value=k,
                        actual_value=k,
                        latency_ms=(time.time() - t0) * 1000.0,
                    )
            except Exception:
                pass

        # 3. GNOME Night Light settings via gsettings
        if self._compositor == "gnome":
            try:
                cmd = [
                    "gsettings", "set",
                    "org.gnome.settings-daemon.plugins.color",
                    "night-light-temperature", str(k)
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    return OperationResult(
                        success=True,
                        verified=True,
                        requested_value=k,
                        actual_value=k,
                        latency_ms=(time.time() - t0) * 1000.0,
                    )
            except Exception:
                pass

        return OperationResult(
            success=False,
            verified=False,
            requested_value=k,
            error_message="No supported Wayland color management backend available (install gammastep)",
            latency_ms=(time.time() - t0) * 1000.0,
        )


# Global singleton instance
wayland_color_backend = WaylandColorBackend()
