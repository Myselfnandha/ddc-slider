"""
Diagnostics and reliability service: permission inspection, backend health,
latency benchmarks, and structured JSON reporting.
"""

from __future__ import annotations

import glob
import grp
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List

from ..core.capability_registry import capability_registry
from ..storage.migrations import LUMATRAY_CONFIG_DIR
from .monitor_service import monitor_service

logger = logging.getLogger(__name__)


class DiagnosticsService:
    """Performs system permissions checks, backend status tests, and generates reports."""

    def check_permissions(self) -> Dict[str, Any]:
        """Check user group memberships and device node permissions."""
        username = os.environ.get("USER", "")
        groups = [g.gr_name for g in grp.getgrall() if username in g.gr_mem]
        try:
            # Check primary group as well
            user_gid = os.getgid()
            primary_group = grp.getgrgid(user_gid).gr_name
            if primary_group not in groups:
                groups.append(primary_group)
        except Exception:
            pass

        in_i2c_group = "i2c" in groups
        in_video_group = "video" in groups

        i2c_devs = glob.glob("/dev/i2c-*")
        i2c_access = {}
        for dev in i2c_devs:
            i2c_access[dev] = {
                "readable": os.access(dev, os.R_OK),
                "writable": os.access(dev, os.W_OK),
            }

        backlight_devs = glob.glob("/sys/class/backlight/*")
        bl_access = {}
        for bl in backlight_devs:
            br_file = os.path.join(bl, "brightness")
            bl_access[bl] = {
                "readable": os.access(br_file, os.R_OK),
                "writable": os.access(br_file, os.W_OK),
            }

        return {
            "user": username,
            "groups": groups,
            "in_i2c_group": in_i2c_group,
            "in_video_group": in_video_group,
            "i2c_devices": i2c_access,
            "backlight_devices": bl_access,
            "all_permissions_ok": in_i2c_group or any(d["writable"] for d in i2c_access.values()),
        }

    def check_tools(self) -> Dict[str, Any]:
        """Verify presence of external CLI helper utilities."""
        tools = ["ddcutil", "brightnessctl", "xrandr", "gammastep", "xprintidle"]
        report = {}
        for tool in tools:
            path = shutil.which(tool)
            installed = (path is not None)
            version = ""
            if installed:
                try:
                    res = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=2)
                    version = res.stdout.strip().splitlines()[0] if res.stdout else ""
                except Exception:
                    pass
            report[tool] = {
                "installed": installed,
                "path": path,
                "version": version,
            }
        return report

    def benchmark_latency(self) -> Dict[str, float]:
        """Measure command round-trip latency to connected hardware backends."""
        results = {}
        # Test xrandr latency
        t0 = time.time()
        try:
            subprocess.run(["xrandr", "--current"], capture_output=True, timeout=3)
            results["xrandr_query_ms"] = round((time.time() - t0) * 1000.0, 1)
        except Exception:
            results["xrandr_query_ms"] = -1.0

        # Test backlight read
        for bl in glob.glob("/sys/class/backlight/*"):
            t0 = time.time()
            try:
                with open(os.path.join(bl, "brightness"), "r") as f:
                    f.read()
                results[f"{os.path.basename(bl)}_read_ms"] = round((time.time() - t0) * 1000.0, 2)
            except Exception:
                pass

        # Test ddcutil detect latency
        t0 = time.time()
        try:
            subprocess.run(["ddcutil", "--version"], capture_output=True, timeout=2)
            results["ddcutil_invoke_ms"] = round((time.time() - t0) * 1000.0, 1)
        except Exception:
            results["ddcutil_invoke_ms"] = -1.0

        return results

    def generate_full_report(self) -> Dict[str, Any]:
        """Generate a complete diagnostic snapshot for support and troubleshooting."""
        monitors = monitor_service.get_monitors()
        monitors_info = []
        for m in monitors:
            caps = capability_registry.get_capabilities(m)
            monitors_info.append({
                "identity": m.to_dict(),
                "capabilities": {
                    "ddc_version": caps.ddc_version,
                    "supported_vcp": [f.to_dict() for f in caps.features.values()],
                    "raw": caps.raw_capabilities,
                }
            })

        return {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "environment": {
                "session_type": os.environ.get("XDG_SESSION_TYPE", "x11"),
                "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "unknown"),
                "display": os.environ.get("DISPLAY", ""),
                "wayland_display": os.environ.get("WAYLAND_DISPLAY", ""),
            },
            "permissions": self.check_permissions(),
            "tools": self.check_tools(),
            "latencies": self.benchmark_latency(),
            "displays": monitors_info,
        }

    def export_report_to_file(self, target_path: Optional[str] = None) -> str:
        """Export full diagnostic report to a JSON file."""
        if not target_path:
            target_path = os.path.join(LUMATRAY_CONFIG_DIR, "diagnostics_report.json")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        report = self.generate_full_report()
        with open(target_path, "w") as f:
            json.dump(report, f, indent=2)
        return target_path


# Global singleton instance
diagnostics_service = DiagnosticsService()
