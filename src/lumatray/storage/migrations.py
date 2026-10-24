"""
Configuration and state migration from legacy ddc-slider to LumaTray.
"""

from __future__ import annotations

import json
import logging
import os
import shutil

logger = logging.getLogger(__name__)

LEGACY_CONFIG_DIR = os.path.expanduser("~/.config/ddc-slider")
LUMATRAY_CONFIG_DIR = os.path.expanduser("~/.config/lumatray")


def migrate_legacy_data_if_needed() -> dict:
    """Migrate settings and state from ddc-slider if LumaTray config does not yet exist."""
    os.makedirs(LUMATRAY_CONFIG_DIR, exist_ok=True)
    target_config = os.path.join(LUMATRAY_CONFIG_DIR, "config.json")

    migrated = {}
    legacy_config = os.path.join(LEGACY_CONFIG_DIR, "config.json")
    if os.path.exists(legacy_config) and not os.path.exists(target_config):
        try:
            with open(legacy_config, "r") as f:
                data = json.load(f)
            logger.info("Migrating existing ddc-slider settings to LumaTray...")
            migrated = data
        except Exception as e:
            logger.warning(f"Failed to read legacy config: {e}")

    return migrated
