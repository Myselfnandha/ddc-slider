"""
Profile and Scene Manager: handles applying profiles, snapshot backups, and diff previews.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

from ..core.events import EventType, events
from ..core.models import Profile
from ..storage.profile_store import profile_store
from .control_engine import control_engine
from .monitor_service import monitor_service

logger = logging.getLogger(__name__)


class ProfileManager:
    """Manages scene profiles, snapshot backups, and pre-apply diffs."""

    def __init__(self):
        self._active_profile_id: Optional[str] = None

    @property
    def active_profile_id(self) -> Optional[str]:
        return self._active_profile_id

    def capture_current_snapshot(self, name: str = "Backup Snapshot") -> dict:
        """Capture the current state of all displays."""
        displays = monitor_service.get_monitors()
        states = {}
        for d in displays:
            st = control_engine.get_state(d.id)
            states[d.id] = {
                "name": d.name,
                "brightness": st.brightness,
                "contrast": st.contrast,
                "color_temp": st.color_temp,
            }
        snapshot = {
            "name": name,
            "created_at": time.time(),
            "displays": states,
        }
        profile_store.save_snapshot(snapshot)
        return snapshot

    def preview_profile_diff(self, profile: Profile) -> Dict[str, Dict[str, Tuple[int, int]]]:
        """Compute the difference between current values and the target profile for preview.
        
        Returns dict: display_id -> { "brightness": (cur, target), ... }
        """
        diff: Dict[str, Dict[str, Tuple[int, int]]] = {}
        displays = monitor_service.get_monitors()

        for d in displays:
            cur = control_engine.get_state(d.id)
            target_br = profile.monitors.get(d.id, {}).get("brightness", profile.master_brightness)
            target_co = profile.monitors.get(d.id, {}).get("contrast", profile.master_contrast)
            target_ct = profile.monitors.get(d.id, {}).get("color_temp", profile.master_color_temp)

            d_diff = {}
            if cur.brightness != target_br:
                d_diff["brightness"] = (cur.brightness, target_br)
            if cur.contrast != target_co:
                d_diff["contrast"] = (cur.contrast, target_co)
            if cur.color_temp != target_ct:
                d_diff["color_temp"] = (cur.color_temp, target_ct)

            if d_diff:
                diff[d.id] = d_diff

        return diff

    def apply_profile(self, profile_or_id: str | Profile) -> bool:
        """Apply a profile across all monitors, taking a snapshot first."""
        if isinstance(profile_or_id, str):
            prof = profile_store.get(profile_or_id) or profile_store.find_by_name(profile_or_id)
        else:
            prof = profile_or_id

        if not prof:
            logger.error(f"Cannot apply profile: profile not found: {profile_or_id}")
            return False

        # 1. Take safety snapshot
        self.capture_current_snapshot(f"Auto-backup before {prof.name}")

        # 2. Apply values
        displays = monitor_service.get_monitors()
        for d in displays:
            target_br = prof.monitors.get(d.id, {}).get("brightness", prof.master_brightness)
            target_co = prof.monitors.get(d.id, {}).get("contrast", prof.master_contrast)
            target_ct = prof.monitors.get(d.id, {}).get("color_temp", prof.master_color_temp)

            control_engine.set_brightness(d.id, target_br)
            control_engine.set_contrast(d.id, target_co)
            control_engine.set_color_temp(d.id, target_ct)

        self._active_profile_id = prof.id
        events.emit(EventType.PROFILE_APPLIED, profile=prof)
        return True

    def restore_last_snapshot(self) -> bool:
        """Restore monitors to the state in the last saved snapshot."""
        snapshot = profile_store.load_snapshot()
        if not snapshot or "displays" not in snapshot:
            return False

        for disp_id, vals in snapshot["displays"].items():
            if "brightness" in vals:
                control_engine.set_brightness(disp_id, vals["brightness"])
            if "contrast" in vals:
                control_engine.set_contrast(disp_id, vals["contrast"])
            if "color_temp" in vals:
                control_engine.set_color_temp(disp_id, vals["color_temp"])

        return True

    def save_current_as_profile(self, name: str, icon: str = "display", description: str = "") -> Profile:
        """Save the current display settings as a new custom user profile."""
        displays = monitor_service.get_monitors()
        mon_dict = {}
        total_br, total_co, total_ct = 0, 0, 0
        for d in displays:
            st = control_engine.get_state(d.id)
            mon_dict[d.id] = {
                "brightness": st.brightness,
                "contrast": st.contrast,
                "color_temp": st.color_temp,
            }
            total_br += st.brightness
            total_co += st.contrast
            total_ct += st.color_temp

        count = max(1, len(displays))
        new_prof = Profile(
            id=f"custom_{int(time.time())}",
            name=name,
            icon=icon,
            description=description,
            monitors=mon_dict,
            master_brightness=round(total_br / count),
            master_contrast=round(total_co / count),
            master_color_temp=round(total_ct / count),
            is_system=False,
            created_at=time.time(),
        )
        profile_store.add_or_update(new_prof)
        return new_prof


# Global singleton instance
profile_manager = ProfileManager()
