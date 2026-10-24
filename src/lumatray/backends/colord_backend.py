"""
Color management coordination and external color service conflict detection.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class ColordBackend:
    """Detects external color managers and coordinates display gamma ownership."""

    EXTERNAL_SERVICES = [
        ("redshift", "Redshift"),
        ("gammastep", "Gammastep"),
        ("wlsunset", "wlsunset"),
        ("fluxgui", "F.lux"),
    ]

    def __init__(self):
        self._paused_services: set[str] = set()

    def check_conflicts(self) -> Optional[str]:
        """Check if another process is actively controlling color temperature."""
        for proc_name, display_name in self.EXTERNAL_SERVICES:
            if self._is_process_running(proc_name):
                return display_name

        # Check GNOME Night Light (only if running GNOME or gsd-color is active)
        if self._is_process_running("gsd-color") or "gnome" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
            if shutil.which("gsettings"):
                try:
                    res = subprocess.run(
                        ["gsettings", "get", "org.gnome.settings-daemon.plugins.color", "night-light-enabled"],
                        capture_output=True, text=True, timeout=2
                    )
                    if res.returncode == 0 and "true" in res.stdout.lower():
                        return "GNOME Night Light"
                except Exception:
                    pass

        return None

    def _is_process_running(self, process_name: str) -> bool:
        try:
            res = subprocess.run(["pgrep", "-x", process_name], capture_output=True, text=True, timeout=2)
            return res.returncode == 0
        except Exception:
            return False

    def pause_service(self, service_name: str) -> bool:
        """Non-destructively pause an external color service if supported."""
        service_lower = service_name.lower()
        if "redshift" in service_lower:
            try:
                subprocess.run(["pkill", "-STOP", "redshift"], timeout=2)
                self._paused_services.add("redshift")
                return True
            except Exception as e:
                logger.warning(f"Failed to pause redshift: {e}")
        elif "gammastep" in service_lower:
            try:
                subprocess.run(["pkill", "-STOP", "gammastep"], timeout=2)
                self._paused_services.add("gammastep")
                return True
            except Exception as e:
                logger.warning(f"Failed to pause gammastep: {e}")
        return False

    def resume_service(self, service_name: str) -> bool:
        """Resume a previously paused color service."""
        service_lower = service_name.lower()
        if "redshift" in service_lower and "redshift" in self._paused_services:
            try:
                subprocess.run(["pkill", "-CONT", "redshift"], timeout=2)
                self._paused_services.discard("redshift")
                return True
            except Exception:
                pass
        elif "gammastep" in service_lower and "gammastep" in self._paused_services:
            try:
                subprocess.run(["pkill", "-CONT", "gammastep"], timeout=2)
                self._paused_services.discard("gammastep")
                return True
            except Exception:
                pass
        return False


# Global singleton instance
colord_backend = ColordBackend()
