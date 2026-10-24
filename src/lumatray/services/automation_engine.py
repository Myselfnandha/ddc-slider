"""
Next-Generation Automation Engine: Circadian curves, ambient sensor adaptation, idle dimming,
and manual override policy.
"""

from __future__ import annotations

import datetime
import logging
import math
import shutil
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple

from ..backends.ambient_light import ambient_backend
from ..core.events import EventType, events
from ..core.validation import clamp_brightness, clamp_contrast, clamp_kelvin
from ..storage.config_store import config_store
from .control_engine import control_engine
from .monitor_service import monitor_service

logger = logging.getLogger(__name__)


def _time_to_minutes(time_str: str) -> int:
    """Parse 'HH:MM' string to minute of day (0-1439)."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


class AutomationEngine:
    """Orchestrates circadian schedules, ambient light sensing, idle dimming, and override rules."""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Manual override tracking
        self._override_active = False
        self._override_until = 0.0
        self._is_idle_dimmed = False
        self._pre_idle_brightness: Dict[str, int] = {}

    def start(self) -> None:
        """Start the automation background worker thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="AutomationEngineThread", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the automation engine."""
        self._running = False

    def notify_manual_override(self) -> None:
        """Call when user manually adjusts a slider or applies a custom profile."""
        timeout_mins = config_store.get("manual_override_timeout_minutes", 45)
        with self._lock:
            self._override_active = True
            self._override_until = time.time() + (timeout_mins * 60)
        logger.info(f"Manual override detected. Automation paused for {timeout_mins} minutes.")
        events.emit(EventType.OVERRIDE_CHANGED, active=True, remaining_seconds=timeout_mins * 60)

    def clear_manual_override(self) -> None:
        """Clear manual override and resume automated control immediately."""
        with self._lock:
            self._override_active = False
            self._override_until = 0.0
        logger.info("Manual override cleared. Automation resumed.")
        events.emit(EventType.OVERRIDE_CHANGED, active=False, remaining_seconds=0)
        self.evaluate_now()

    def is_enabled(self) -> bool:
        """Check if circadian automation is enabled."""
        return bool(config_store.get("circadian_enabled", True))

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable circadian automation."""
        config_store.set("circadian_enabled", enabled)
        if enabled:
            self.clear_manual_override()
            self.evaluate_now()
        logger.info(f"Automation enabled set to {enabled}")
        events.emit(EventType.AUTOMATION_STATE_CHANGED, enabled=enabled)

    def toggle_auto_mode(self) -> bool:
        """Toggle circadian automation on/off and return new state."""
        new_state = not self.is_enabled()
        self.set_enabled(new_state)
        return new_state

    def is_override_active(self) -> bool:
        with self._lock:
            if not self._override_active:
                return False
            if time.time() > self._override_until:
                self._override_active = False
                return False
            return True

    def get_override_remaining_seconds(self) -> int:
        with self._lock:
            if not self._override_active:
                return 0
            rem = int(self._override_until - time.time())
            return max(0, rem)

    def evaluate_circadian_target(self, now: Optional[datetime.datetime] = None) -> Tuple[int, int, int]:
        """Compute current circadian target (brightness, contrast, kelvin) using cosine easing."""
        waypoints = config_store.get("circadian_waypoints", [])
        if not waypoints:
            return (100, 50, 6500)

        now = now or datetime.datetime.now()
        cur_min = now.hour * 60 + now.minute + now.second / 60.0

        # Sort waypoints by time
        sorted_wp = sorted(waypoints, key=lambda w: _time_to_minutes(w["time"]))
        n = len(sorted_wp)

        # Find previous and next waypoints
        prev_idx = n - 1
        next_idx = 0
        for i, wp in enumerate(sorted_wp):
            if cur_min >= _time_to_minutes(wp["time"]):
                prev_idx = i
            else:
                next_idx = i
                break
        else:
            next_idx = 0

        wp_prev = sorted_wp[prev_idx]
        wp_next = sorted_wp[next_idx]

        t_prev = _time_to_minutes(wp_prev["time"])
        t_next = _time_to_minutes(wp_next["time"])
        if t_next <= t_prev:
            t_next += 1440

        adj_cur = cur_min if cur_min >= t_prev else cur_min + 1440
        span = t_next - t_prev
        progress = max(0.0, min(1.0, (adj_cur - t_prev) / span)) if span > 0 else 0.0

        # Smooth cosine interpolation
        ease = (1.0 - math.cos(progress * math.pi)) / 2.0

        br = round(wp_prev["brightness"] + (wp_next["brightness"] - wp_prev["brightness"]) * ease)
        co = round(wp_prev["contrast"] + (wp_next["contrast"] - wp_prev["contrast"]) * ease)
        ct = round(wp_prev["color_temp"] + (wp_next["color_temp"] - wp_prev["color_temp"]) * ease)

        return clamp_brightness(br), clamp_contrast(co), clamp_kelvin(ct)

    def evaluate_now(self) -> None:
        """Trigger an immediate automation evaluation cycle."""
        if not config_store.get("circadian_enabled", True):
            return

        if self.is_override_active():
            return

        # Check idle dimming
        if self._check_and_handle_idle():
            return

        # 1. Circadian targets
        target_br, target_co, target_ct = self.evaluate_circadian_target()

        # 2. Ambient light sensor adjustment if enabled
        if config_store.get("ambient_sensor_enabled", False) and ambient_backend.is_available():
            lux = ambient_backend.get_lux()
            if lux is not None:
                amb_br = ambient_backend.compute_target_brightness(lux)
                # Blend circadian schedule (40%) with ambient sensor (60%)
                target_br = clamp_brightness(round(0.4 * target_br + 0.6 * amb_br))

        # 3. Apply to monitors
        for d in monitor_service.get_monitors():
            control_engine.set_brightness(d.id, target_br, notify_user=False)
            control_engine.set_contrast(d.id, target_co, notify_user=False)
            control_engine.set_color_temp(d.id, target_ct, notify_user=False)

    def _check_and_handle_idle(self) -> bool:
        """Check if desktop is idle and dim displays if configured."""
        if not config_store.get("idle_dimming_enabled", False):
            if self._is_idle_dimmed:
                self._restore_from_idle()
            return False

        idle_seconds = self._get_system_idle_seconds()
        threshold_seconds = config_store.get("idle_dimming_minutes", 10) * 60

        if idle_seconds >= threshold_seconds and not self._is_idle_dimmed:
            # Dim displays
            self._is_idle_dimmed = True
            idle_target = config_store.get("idle_brightness_target", 15)
            self._pre_idle_brightness.clear()
            for d in monitor_service.get_monitors():
                self._pre_idle_brightness[d.id] = control_engine.get_state(d.id).brightness
                control_engine.set_brightness(d.id, idle_target, notify_user=False)
            logger.info("System idle detected: dimmed displays.")
            return True
        elif idle_seconds < threshold_seconds and self._is_idle_dimmed:
            self._restore_from_idle()
            return False

        return self._is_idle_dimmed

    def _restore_from_idle(self) -> None:
        self._is_idle_dimmed = False
        for disp_id, orig_br in self._pre_idle_brightness.items():
            control_engine.set_brightness(disp_id, orig_br, notify_user=False)
        logger.info("System resumed from idle: restored monitor brightness.")

    @staticmethod
    def _get_system_idle_seconds() -> int:
        if shutil.which("xprintidle"):
            try:
                res = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    return int(int(res.stdout.strip()) / 1000)
            except Exception:
                pass
        return 0

    def _loop(self):
        """Main periodic evaluation loop (ticks every 10 seconds)."""
        while self._running:
            try:
                self.evaluate_now()
            except Exception as e:
                logger.error(f"Error in automation engine loop: {e}", exc_info=True)
            time.sleep(10)


# Global singleton instance
automation_engine = AutomationEngine()
