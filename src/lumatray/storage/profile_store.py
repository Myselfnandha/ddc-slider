"""
Profile and Scene store for LumaTray with snapshot backups and JSON import/export.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Dict, List, Optional

from ..core.models import Profile
from .migrations import LUMATRAY_CONFIG_DIR

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROFILES = [
    Profile(
        id="daylight",
        name="Daylight ☀",
        icon="weather-clear",
        description="Full daylight brightness and crisp neutral 6500K color",
        master_brightness=100,
        master_contrast=75,
        master_color_temp=6500,
        is_system=True,
    ),
    Profile(
        id="reading",
        name="Reading 📖",
        icon="accessories-text-editor",
        description="Gentle brightness and warm 5000K white point for comfortable reading",
        master_brightness=70,
        master_contrast=50,
        master_color_temp=5000,
        is_system=True,
    ),
    Profile(
        id="coding",
        name="Coding 💻",
        icon="applications-development",
        description="Balanced contrast and 5500K for high code readability without eye fatigue",
        master_brightness=80,
        master_contrast=60,
        master_color_temp=5500,
        is_system=True,
    ),
    Profile(
        id="movie",
        name="Movie 🎬",
        icon="video-display",
        description="Cinematic low brightness with punchy contrast and warm 3500K tone",
        master_brightness=45,
        master_contrast=60,
        master_color_temp=3500,
        is_system=True,
    ),
    Profile(
        id="gaming",
        name="Gaming 🎮",
        icon="input-gaming",
        description="High brightness, vibrant dynamic range and neutral color",
        master_brightness=90,
        master_contrast=70,
        master_color_temp=6500,
        is_system=True,
    ),
    Profile(
        id="night",
        name="Night Owl 🌙",
        icon="weather-clear-night",
        description="Low brightness and soothing warm 2700K amber glow for nighttime work",
        master_brightness=25,
        master_contrast=45,
        master_color_temp=2700,
        is_system=True,
    ),
    Profile(
        id="candlelight",
        name="Candlelight 🕯",
        icon="weather-few-clouds-night",
        description="Minimum dimness and ultra-warm 2200K orange spectrum before sleep",
        master_brightness=15,
        master_contrast=40,
        master_color_temp=2200,
        is_system=True,
    ),
]


class ProfileStore:
    """Store for scene profiles and snapshot backups."""

    def __init__(self, config_dir: str = LUMATRAY_CONFIG_DIR):
        self.config_dir = config_dir
        self.profiles_path = os.path.join(self.config_dir, "profiles.json")
        self.backup_snapshot_path = os.path.join(self.config_dir, "last_snapshot.json")
        self._profiles: Dict[str, Profile] = {}
        self.load()

    def load(self) -> None:
        """Load profiles from disk or populate system defaults."""
        os.makedirs(self.config_dir, exist_ok=True)
        # Seed system defaults
        for p in DEFAULT_SYSTEM_PROFILES:
            self._profiles[p.id] = p

        if os.path.exists(self.profiles_path):
            try:
                with open(self.profiles_path, "r") as f:
                    data = json.load(f)
                for item in data:
                    prof = Profile.from_dict(item)
                    self._profiles[prof.id] = prof
            except Exception as e:
                logger.error(f"Error reading profiles from {self.profiles_path}: {e}")

    def save(self) -> None:
        """Atomically persist custom profiles to disk."""
        os.makedirs(self.config_dir, exist_ok=True)
        try:
            custom_list = [p.to_dict() for p in self._profiles.values() if not p.is_system]
            with tempfile.NamedTemporaryFile("w", dir=self.config_dir, delete=False) as tf:
                json.dump(custom_list, tf, indent=2)
                temp_name = tf.name
            os.replace(temp_name, self.profiles_path)
        except Exception as e:
            logger.error(f"Error saving profiles to {self.profiles_path}: {e}")

    def list_all(self) -> List[Profile]:
        return list(self._profiles.values())

    def get(self, profile_id: str) -> Optional[Profile]:
        return self._profiles.get(profile_id)

    def find_by_name(self, name: str) -> Optional[Profile]:
        name_lower = name.lower().strip()
        for p in self._profiles.values():
            if p.name.lower().strip() == name_lower or p.id.lower() == name_lower:
                return p
        return None

    def add_or_update(self, profile: Profile) -> None:
        self._profiles[profile.id] = profile
        self.save()

    def delete(self, profile_id: str) -> bool:
        if profile_id in self._profiles and not self._profiles[profile_id].is_system:
            del self._profiles[profile_id]
            self.save()
            return True
        return False

    def save_snapshot(self, snapshot_data: dict) -> None:
        """Save a snapshot backup of current monitor states before profile change."""
        os.makedirs(self.config_dir, exist_ok=True)
        try:
            snapshot_data["timestamp"] = time.time()
            with open(self.backup_snapshot_path, "w") as f:
                json.dump(snapshot_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save monitor snapshot: {e}")

    def load_snapshot(self) -> Optional[dict]:
        """Load the last snapshot backup if available."""
        if os.path.exists(self.backup_snapshot_path):
            try:
                with open(self.backup_snapshot_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def export_profile_to_json(self, profile_id: str, filepath: str) -> bool:
        prof = self.get(profile_id)
        if not prof:
            return False
        try:
            with open(filepath, "w") as f:
                json.dump(prof.to_dict(), f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Export profile failed: {e}")
            return False

    def import_profile_from_json(self, filepath: str) -> Optional[Profile]:
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            prof = Profile.from_dict(data)
            prof.is_system = False
            self.add_or_update(prof)
            return prof
        except Exception as e:
            logger.error(f"Import profile failed: {e}")
            return None


# Global singleton instance
profile_store = ProfileStore()
