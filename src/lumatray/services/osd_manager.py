"""
OSD (On-Screen Display) manager coordinating visual feedback popups.
"""

from __future__ import annotations

import logging
from ..core.events import EventType, events
from ..storage.config_store import config_store

logger = logging.getLogger(__name__)


class OSDManager:
    """Dispatches on-screen display notifications for brightness, contrast, and color temperature."""

    def show(self, feature: str, value: int, label: str = "") -> None:
        """Trigger an OSD notification.
        
        feature: 'brightness', 'contrast', 'color_temp'
        value: current integer value
        label: optional monitor name or descriptor
        """
        if not config_store.get("show_osd", True):
            return

        duration_ms = config_store.get("osd_duration_ms", 1500)
        events.emit(
            EventType.OSD_REQUESTED,
            feature=feature,
            value=value,
            label=label,
            duration_ms=duration_ms,
        )


# Global singleton instance
osd_manager = OSDManager()
