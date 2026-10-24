"""
Thread-safe event bus for decoupled communication across LumaTray components.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List

from gi.repository import GLib

logger = logging.getLogger(__name__)


class EventType:
    MONITORS_CHANGED = "monitors_changed"
    VALUE_CHANGED = "value_changed"
    PROFILE_APPLIED = "profile_applied"
    AUTOMATION_STATE_CHANGED = "automation_state_changed"
    OVERRIDE_CHANGED = "override_changed"
    BACKEND_STATUS_CHANGED = "backend_status_changed"
    OSD_REQUESTED = "osd_requested"
    DIAGNOSTIC_LOG = "diagnostic_log"
    ERROR_OCCURRED = "error_occurred"


class EventBus:
    """Thread-safe event bus supporting synchronous and GTK main-thread dispatches."""

    def __init__(self):
        self._subscribers: Dict[str, List[tuple[Callable[..., Any], bool]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable[..., Any], on_main_thread: bool = False):
        """Subscribe a callback to an event.
        
        If on_main_thread is True, the callback will always be executed on the
        GLib/GTK main thread via GLib.idle_add.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append((callback, on_main_thread))

    def unsubscribe(self, event_type: str, callback: Callable[..., Any]):
        """Unsubscribe a callback."""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    (cb, omt) for cb, omt in self._subscribers[event_type] if cb != callback
                ]

    def emit(self, event_type: str, **kwargs):
        """Emit an event to all subscribers."""
        with self._lock:
            listeners = list(self._subscribers.get(event_type, []))

        for callback, on_main_thread in listeners:
            if on_main_thread:
                # Dispatch safely to GTK main loop
                def _invoke(cb=callback, kw=kwargs):
                    try:
                        cb(**kw)
                    except Exception as e:
                        logger.error(f"Error in main-thread event listener for {event_type}: {e}", exc_info=True)
                    return False
                GLib.idle_add(_invoke)
            else:
                try:
                    callback(**kwargs)
                except Exception as e:
                    logger.error(f"Error in event listener for {event_type}: {e}", exc_info=True)


# Global singleton instance
events = EventBus()
