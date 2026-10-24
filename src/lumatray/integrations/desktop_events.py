"""
Desktop environment event listener: suspend/resume detection via systemd logind D-Bus.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class DesktopEventListener:
    """Listens for system sleep and wake events to restore display states."""

    def __init__(self, on_resume_callback=None):
        self.on_resume_callback = on_resume_callback
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start listening for systemd logind PrepareForSleep signals."""
        self._running = True
        self._thread = threading.Thread(target=self._listen_dbus, name="LogindSleepWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _listen_dbus(self):
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio, GLib

            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

            def _on_signal(connection, sender_name, object_path, interface_name, signal_name, parameters, user_data):
                if signal_name == "PrepareForSleep":
                    going_to_sleep = parameters.unpack()[0]
                    if not going_to_sleep:
                        logger.info("System resumed from sleep! Re-evaluating display configurations...")
                        time.sleep(2.0)
                        if self.on_resume_callback:
                            self.on_resume_callback()

            bus.signal_subscribe(
                "org.freedesktop.login1",
                "org.freedesktop.login1.Manager",
                "PrepareForSleep",
                "/org/freedesktop/login1",
                None,
                Gio.DBusSignalFlags.NONE,
                _on_signal,
                None,
            )
        except Exception as e:
            logger.debug(f"Could not subscribe to systemd sleep events: {e}")


# Global instance
desktop_events = DesktopEventListener()
