"""
Desktop hotkey triggers and shortcut helpers.
"""

from __future__ import annotations

import logging
from ..services.control_engine import control_engine
from ..services.monitor_service import monitor_service
from ..services.osd_manager import osd_manager
from ..storage.config_store import config_store

logger = logging.getLogger(__name__)


class HotkeyManager:
    """Provides hotkey action endpoints for desktop keybinding integration."""

    @staticmethod
    def step_brightness(delta: int) -> None:
        """Step master brightness up or down by delta percentage."""
        mons = monitor_service.get_monitors()
        if not mons:
            return
        cur_br = control_engine.get_state(mons[0].id).brightness
        new_br = max(0, min(100, cur_br + delta))
        control_engine.set_master_brightness(new_br)
        osd_manager.show("brightness", new_br)

    @staticmethod
    def step_contrast(delta: int) -> None:
        """Step master contrast up or down by delta percentage."""
        mons = monitor_service.get_monitors()
        if not mons:
            return
        cur_co = control_engine.get_state(mons[0].id).contrast
        new_co = max(0, min(100, cur_co + delta))
        control_engine.set_master_contrast(new_co)
        osd_manager.show("contrast", new_co)

    @staticmethod
    def step_color_temp(delta_k: int) -> None:
        """Step master color temperature by delta Kelvin."""
        mons = monitor_service.get_monitors()
        if not mons:
            return
        cur_k = control_engine.get_state(mons[0].id).color_temp
        new_k = max(1000, min(10000, cur_k + delta_k))
        control_engine.set_master_color_temp(new_k)
        osd_manager.show("color_temp", new_k)


hotkeys = HotkeyManager()
