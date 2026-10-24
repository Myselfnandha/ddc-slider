"""
Persistent configuration store for LumaTray.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
from typing import Any, Dict

from .migrations import LUMATRAY_CONFIG_DIR, migrate_legacy_data_if_needed

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    # General UI & Personalization
    "theme": "system",                     # "system", "dark", "light"
    "compact_mode": False,
    "slider_step": 5,                      # 1, 5, 10
    "show_contrast_slider": True,
    "show_color_temp_slider": True,
    "show_tray_icon": True,
    "tray_mode": "auto",                   # "auto", "appindicator", "statusicon"
    "close_to_tray": True,
    "autostart": False,
    
    # Range limits
    "brightness_min": 1,
    "brightness_max": 100,
    "color_temp_min": 1500,
    "color_temp_max": 6500,

    # Hardware & VCP
    "vcp_brightness": 0x10,
    "vcp_contrast": 0x12,
    "enable_advanced_vcp": False,          # Allow RGB gains and input switching
    "include_internal_display": True,

    # Smart Automation & Circadian
    "circadian_enabled": True,
    "circadian_waypoints": [
        {"name": "Dawn 🌄", "time": "05:30", "brightness": 25, "contrast": 45, "color_temp": 3400},
        {"name": "Morning 🌅", "time": "07:30", "brightness": 70, "contrast": 65, "color_temp": 5000},
        {"name": "Daylight ☀", "time": "10:00", "brightness": 100, "contrast": 75, "color_temp": 6500},
        {"name": "Sunset 🌇", "time": "17:30", "brightness": 70, "contrast": 65, "color_temp": 4500},
        {"name": "Night 🌙", "time": "20:30", "brightness": 45, "contrast": 55, "color_temp": 3400},
        {"name": "Late Night 🕯", "time": "23:00", "brightness": 25, "contrast": 45, "color_temp": 2700},
    ],
    "manual_override_timeout_minutes": 45,
    "ambient_sensor_enabled": False,
    "idle_dimming_enabled": False,
    "idle_dimming_minutes": 10,
    "idle_brightness_target": 15,
    "hotplug_reconnect_recovery": True,

    # OSD
    "show_osd": True,
    "osd_duration_ms": 1500,
}


class ConfigStore:
    """Thread-safe persistent configuration store."""

    def __init__(self, config_dir: str = LUMATRAY_CONFIG_DIR):
        self.config_dir = config_dir
        self.config_path = os.path.join(self.config_dir, "config.json")
        self._data: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """Load configuration from disk, applying legacy migrations if needed."""
        os.makedirs(self.config_dir, exist_ok=True)
        migrated = migrate_legacy_data_if_needed()
        if migrated:
            self._data.update(migrated)
            self.save()

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    disk_data = json.load(f)
                self._data.update(disk_data)
            except Exception as e:
                logger.error(f"Error loading config from {self.config_path}: {e}")

    def save(self) -> None:
        """Atomically persist configuration to disk."""
        os.makedirs(self.config_dir, exist_ok=True)
        try:
            dir_name = os.path.dirname(self.config_path)
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False) as tf:
                json.dump(self._data, tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, self.config_path)
        except Exception as e:
            logger.error(f"Error saving config to {self.config_path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        self._data[key] = value
        if auto_save:
            self.save()

    def update(self, mapping: Dict[str, Any], auto_save: bool = True) -> None:
        self._data.update(mapping)
        if auto_save:
            self.save()

    @property
    def all(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data)


# Global singleton instance
config_store = ConfigStore()
