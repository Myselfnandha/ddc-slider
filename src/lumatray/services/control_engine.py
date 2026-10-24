"""
Central control engine orchestrating brightness, contrast, and color operations across backends.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from ..backends.backlight_sysfs import backlight_backend
from ..backends.color_x11 import x11_color_backend
from ..backends.ddcutil_backend import ddc_backend
from ..core.events import EventType, events
from ..core.models import DisplayIdentity, DisplayType, MonitorState, OperationResult
from ..core.validation import clamp_brightness, clamp_contrast, clamp_kelvin
from .color_service import color_service
from .monitor_service import monitor_service

logger = logging.getLogger(__name__)


class ControlEngine:
    """Thread-safe orchestrator for all monitor value adjustments."""

    def __init__(self):
        self._states: Dict[str, MonitorState] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="LumaEngineWorker")


        # Subscribe to monitor changes to refresh states
        events.subscribe(EventType.MONITORS_CHANGED, self._on_monitors_changed)

    def _on_monitors_changed(self, monitors: List[DisplayIdentity]):
        with self._lock:
            # Retain existing states for monitors that stayed connected, create defaults for new ones
            for m in monitors:
                if m.id not in self._states:
                    self._states[m.id] = MonitorState(
                        display_id=m.id,
                        brightness=50,
                        contrast=50,
                        color_temp=6500,
                        color_mode=color_service.get_color_mode_for_display(m),
                    )

    def get_state(self, display_id: str) -> MonitorState:
        with self._lock:
            if display_id not in self._states:
                m = monitor_service.get_monitor_by_id(display_id)
                mode = color_service.get_color_mode_for_display(m) if m else "gamma"
                self._states[display_id] = MonitorState(display_id=display_id, color_mode=mode)
            return self._states[display_id]

    def get_all_states(self) -> Dict[str, MonitorState]:
        with self._lock:
            return dict(self._states)

    def set_brightness(self, display_id: str, value: int, notify_user: bool = True) -> OperationResult:
        """Set brightness for a single display."""
        val = clamp_brightness(value)
        disp = monitor_service.get_monitor_by_id(display_id)
        if not disp:
            return OperationResult(success=False, error_message=f"Display {display_id} not found")

        # Update cached state
        with self._lock:
            if display_id in self._states:
                self._states[display_id].brightness = val

        if notify_user:
            events.emit(EventType.VALUE_CHANGED, display_id=display_id, feature="brightness", value=val)

        # Route to appropriate backend asynchronously
        def _dispatch():
            if disp.display_type == DisplayType.INTERNAL_BACKLIGHT:
                return backlight_backend.set_brightness(val)
            elif disp.display_type == DisplayType.EXTERNAL_DDC:
                return ddc_backend.set_vcp(disp.bus, 0x10, val, async_write=True)
            elif disp.connector_name:
                frac = round(val / 100.0, 2)
                import subprocess
                subprocess.run(["xrandr", "--output", disp.connector_name, "--brightness", str(frac)],
                               capture_output=True, timeout=4)
                return OperationResult(success=True, verified=False, requested_value=val, actual_value=val)
            return OperationResult(success=False, error_message="No backend available")

        self._executor.submit(_dispatch)
        return OperationResult(success=True, verified=False, requested_value=val, actual_value=val)

    def set_contrast(self, display_id: str, value: int, notify_user: bool = True) -> OperationResult:
        """Set contrast for a single display."""
        val = clamp_contrast(value)
        disp = monitor_service.get_monitor_by_id(display_id)
        if not disp:
            return OperationResult(success=False, error_message=f"Display {display_id} not found")

        with self._lock:
            if display_id in self._states:
                self._states[display_id].contrast = val

        if notify_user:
            events.emit(EventType.VALUE_CHANGED, display_id=display_id, feature="contrast", value=val)

        def _dispatch():
            if disp.display_type == DisplayType.EXTERNAL_DDC:
                return ddc_backend.set_vcp(disp.bus, 0x12, val, async_write=True)
            elif disp.connector_name:
                cur_k = self.get_state(display_id).color_temp
                return x11_color_backend.apply_gamma(
                    disp.connector_name, kelvin=cur_k, contrast=val, is_software_contrast=True
                )
            return OperationResult(success=False, error_message="No contrast backend available")

        self._executor.submit(_dispatch)
        return OperationResult(success=True, verified=False, requested_value=val, actual_value=val)

    def set_color_temp(self, display_id: str, kelvin: int, notify_user: bool = True) -> OperationResult:
        """Set color temperature for a single display."""
        k = clamp_kelvin(kelvin)
        disp = monitor_service.get_monitor_by_id(display_id)
        if not disp:
            return OperationResult(success=False, error_message=f"Display {display_id} not found")

        with self._lock:
            if display_id in self._states:
                self._states[display_id].color_temp = k

        if notify_user:
            events.emit(EventType.VALUE_CHANGED, display_id=display_id, feature="color_temp", value=k)

        def _dispatch():
            return color_service.set_color_temperature(disp, k)

        self._executor.submit(_dispatch)
        return OperationResult(success=True, verified=False, requested_value=k, actual_value=k)

    def set_master_brightness(self, value: int) -> None:
        """Set brightness uniformly across all connected displays."""
        val = clamp_brightness(value)
        for disp in monitor_service.get_monitors():
            self.set_brightness(disp.id, val)

    def set_master_contrast(self, value: int) -> None:
        """Set contrast uniformly across all connected displays."""
        val = clamp_contrast(value)
        for disp in monitor_service.get_monitors():
            self.set_contrast(disp.id, val)

    def set_master_color_temp(self, kelvin: int) -> None:
        """Set color temperature uniformly across all connected displays."""
        k = clamp_kelvin(kelvin)
        for disp in monitor_service.get_monitors():
            self.set_color_temp(disp.id, k)


# Global singleton instance
control_engine = ControlEngine()
