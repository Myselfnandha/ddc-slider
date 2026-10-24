"""
Application lifecycle manager, single-instance coordination, and service startup.
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import Any, Dict, Optional
from gi.repository import GLib, Gtk

from .core.events import EventType, events
from .integrations.dbus_service import IPCServer
from .integrations.desktop_events import desktop_events
from .services.automation_engine import automation_engine
from .services.control_engine import control_engine
from .services.diagnostics import diagnostics_service
from .services.monitor_service import monitor_service
from .services.profile_manager import profile_manager
from .storage.config_store import config_store
from .ui.main_window import MainWindow
from .ui.osd import OSDWindow
from .ui.quick_panel import QuickPanelWindow
from .ui.styles import apply_theme
from .ui.tray import TrayAdapter

logger = logging.getLogger(__name__)


class LumaTrayApplication:
    """Central application coordinator."""

    def __init__(self):
        self.main_window: MainWindow | None = None
        self.quick_panel: QuickPanelWindow | None = None
        self.osd_window: OSDWindow | None = None
        self.tray_adapter: TrayAdapter | None = None
        self.ipc_server: IPCServer | None = None

    def run(self, start_hidden: bool = True) -> int:
        """Initialize all services and enter the GTK main loop."""
        logger.info("Starting LumaTray Monitor Control Suite...")

        # 1. Apply UI theme
        apply_theme()

        # 2. Initialize and discover monitors
        monitor_service.discover_monitors()
        monitor_service.start_hotplug_watcher()

        # 3. Start automation engine and desktop power listeners
        automation_engine.start()
        desktop_events.start()

        # 4. Initialize windows
        self.osd_window = OSDWindow()
        self.main_window = MainWindow()
        self.quick_panel = QuickPanelWindow(on_open_suite=self.show_main_window)

        # 5. Initialize Tray
        if config_store.get("show_tray_icon", True):
            self.tray_adapter = TrayAdapter(
                on_toggle_quick_panel=self.toggle_quick_panel,
                on_open_suite_window=self.show_main_window,
                on_quit=self.quit,
            )

        # 6. Start IPC server
        self.ipc_server = IPCServer(request_handler=self._handle_ipc_request)
        self.ipc_server.start()

        # 7. Setup clean signal handlers
        signal.signal(signal.SIGINT, lambda *_: GLib.idle_add(self.quit))
        signal.signal(signal.SIGTERM, lambda *_: GLib.idle_add(self.quit))

        if not start_hidden:
            self.show_main_window()

        Gtk.main()
        return 0

    def toggle_quick_panel(self, x: int = 100, y: int = 100, anchor_area: Optional[tuple] = None):
        if self.quick_panel:
            self.quick_panel.toggle(x, y, anchor_area)

    def show_main_window(self):
        if self.main_window:
            self.main_window.show_all()
            self.main_window.present()

    def _handle_ipc_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Process an IPC request sent from CLI or another process."""
        action = req.get("action", "")

        if action == "show":
            def _show_smart():
                if self.tray_adapter and self.tray_adapter._status_icon:
                    geom = self.tray_adapter._status_icon.get_geometry()
                    if geom and geom[0]:
                        area, orient = geom[2], geom[3]
                        self.toggle_quick_panel(
                            area.x + area.width // 2,
                            area.y + area.height // 2,
                            anchor_area=(area.x, area.y, area.width, area.height, orient),
                        )
                        return
                req_x = req.get("x")
                req_y = req.get("y")
                if req_x is not None and req_y is not None:
                    self.toggle_quick_panel(req_x, req_y)
                else:
                    self.toggle_quick_panel()

            GLib.idle_add(_show_smart)
            return {"status": "ok", "action": "show"}

        if action == "show_main":
            GLib.idle_add(self.show_main_window)
            return {"status": "ok", "action": "show_main"}

        if action == "list_monitors":
            monitors = monitor_service.get_monitors()
            data = []
            for m in monitors:
                st = control_engine.get_state(m.id)
                data.append({
                    "id": m.id,
                    "name": m.name,
                    "type": m.display_type.value,
                    "connector": m.connector_name,
                    "bus": m.bus,
                    "brightness": st.brightness,
                    "contrast": st.contrast,
                    "color_temp": st.color_temp,
                })
            return {"status": "ok", "monitors": data}

        if action == "set":
            feat = req.get("feature", "").lower()
            val = req.get("value")
            disp_id = req.get("display_id")
            if val is None:
                return {"status": "error", "message": "Missing value"}

            if disp_id:
                if feat == "brightness":
                    control_engine.set_brightness(disp_id, val)
                elif feat == "contrast":
                    control_engine.set_contrast(disp_id, val)
                elif feat in ("kelvin", "color_temp"):
                    control_engine.set_color_temp(disp_id, val)
            else:
                if feat == "brightness":
                    control_engine.set_master_brightness(val)
                elif feat == "contrast":
                    control_engine.set_master_contrast(val)
                elif feat in ("kelvin", "color_temp"):
                    control_engine.set_master_color_temp(val)

            automation_engine.notify_manual_override()
            return {"status": "ok", "feature": feat, "value": val}

        if action == "apply_profile":
            p_name = req.get("profile")
            success = profile_manager.apply_profile(p_name)
            return {"status": "ok" if success else "error", "profile": p_name}

        if action == "toggle_night":
            mons = monitor_service.get_monitors()
            if mons:
                cur_k = control_engine.get_state(mons[0].id).color_temp
                tgt = "daylight" if cur_k < 4500 else "night"
                profile_manager.apply_profile(tgt)
                return {"status": "ok", "active_profile": tgt}
            return {"status": "error", "message": "No monitors"}

        if action == "circadian_status":
            t_br, t_co, t_ct = automation_engine.evaluate_circadian_target()
            return {
                "status": "ok",
                "enabled": config_store.get("circadian_enabled", True),
                "target_brightness": t_br,
                "target_contrast": t_co,
                "target_kelvin": t_ct,
                "override_active": automation_engine.is_override_active(),
                "override_remaining_seconds": automation_engine.get_override_remaining_seconds(),
            }

        if action == "toggle_auto":
            new_state = automation_engine.toggle_auto_mode()
            return {"status": "ok", "enabled": new_state}

        return {"status": "error", "message": f"Unknown action '{action}'"}

    def quit(self):
        """Clean shutdown of all workers and background loops."""
        logger.info("Shutting down LumaTray...")
        if self.ipc_server:
            self.ipc_server.stop()
        monitor_service.stop_hotplug_watcher()
        automation_engine.stop()
        desktop_events.stop()
        Gtk.main_quit()
