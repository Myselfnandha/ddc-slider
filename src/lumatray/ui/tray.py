"""
System Tray Adapter supporting Gtk.StatusIcon (native direct left-click for desktop panels)
and AyatanaAppIndicator / AppIndicator3 fallback.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional
from gi.repository import Gdk, GLib, Gtk

from ..core.events import EventType, events
from ..services.automation_engine import automation_engine
from ..services.control_engine import control_engine
from ..services.monitor_service import monitor_service
from ..services.osd_manager import osd_manager
from ..services.profile_manager import profile_manager
from ..storage.config_store import config_store
from ..storage.profile_store import profile_store

logger = logging.getLogger(__name__)


class TrayAdapter:
    """Manages the system tray icon, context menu, and click interactions."""

    def __init__(
        self,
        on_toggle_quick_panel: Callable[..., None],
        on_open_suite_window: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        self.on_toggle_quick_panel = on_toggle_quick_panel
        self.on_open_suite_window = on_open_suite_window
        self.on_quit = on_quit

        self._indicator = None
        self._status_icon = None
        self._init_tray()

        events.subscribe(EventType.AUTOMATION_STATE_CHANGED, self._on_automation_changed, on_main_thread=True)
        events.subscribe(EventType.OVERRIDE_CHANGED, self._on_automation_changed, on_main_thread=True)

    def _init_tray(self):
        tray_mode = config_store.get("tray_mode", "auto")
        is_wayland = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland")
        initialized = False

        # 1. On X11 / XFCE / MATE, prioritize Gtk.StatusIcon for native direct left-click popup on desktop panels
        if not is_wayland and tray_mode in ("auto", "statusicon"):
            try:
                self._status_icon = Gtk.StatusIcon.new_from_icon_name("display-brightness-symbolic")
                self._status_icon.set_title("LumaTray")
                self._status_icon.set_tooltip_text("LumaTray Monitor Control")
                self._status_icon.connect("activate", self._on_status_icon_activate)
                self._status_icon.connect("popup-menu", self._on_status_icon_popup)
                self._status_icon.connect("scroll-event", self._on_status_icon_scroll)
                self._status_icon.set_visible(True)

                def _check_embedded():
                    if self._status_icon and not self._status_icon.is_embedded():
                        logger.warning("Gtk.StatusIcon not embedded after timeout, falling back to AppIndicator...")
                        self._status_icon.set_visible(False)
                        self._status_icon = None
                        self._fallback_to_appindicator()
                    return False

                GLib.timeout_add(1500, _check_embedded)
                initialized = True
                logger.info("Initialized system tray using Gtk.StatusIcon (native direct left-click).")
            except Exception as e:
                logger.debug(f"Gtk.StatusIcon unavailable: {e}")

        # 2. Fallback to AppIndicator (Wayland, GNOME, or when StatusIcon fails)
        if not initialized:
            self._fallback_to_appindicator()

    def _fallback_to_appindicator(self):
        try:
            import gi
            try:
                gi.require_version("AyatanaAppIndicator3", "0.1")
                from gi.repository import AyatanaAppIndicator3 as appindicator
            except (ValueError, ImportError):
                gi.require_version("AppIndicator3", "0.1")
                from gi.repository import AppIndicator3 as appindicator

            self._indicator = appindicator.Indicator.new(
                "lumatray",
                "display-brightness-symbolic",
                appindicator.IndicatorCategory.HARDWARE,
            )
            self._indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
            self._indicator.set_menu(self._build_menu())

            if hasattr(self._indicator, "connect"):
                try:
                    self._indicator.connect("scroll-event", self._on_indicator_scroll)
                except Exception:
                    pass
            logger.info("Initialized system tray using AppIndicator.")
        except Exception as e:
            logger.error(f"Failed to initialize AppIndicator fallback: {e}")

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        # 1. Quick Control Panel
        item_quick = Gtk.MenuItem(label="🎛 Quick Panel")
        item_quick.connect("activate", lambda m: self._on_menu_open_quick_panel())
        menu.append(item_quick)

        # 2. Open Full Suite
        item_suite = Gtk.MenuItem(label="🖥 Monitor Control Suite")
        item_suite.connect("activate", lambda m: self.on_open_suite_window())
        menu.append(item_suite)

        menu.append(Gtk.SeparatorMenuItem())

        # 3. Presets Submenu
        presets_item = Gtk.MenuItem(label="🎨 Scene Presets")
        presets_menu = Gtk.Menu()
        for prof in profile_store.list_all():
            p_item = Gtk.MenuItem(label=prof.name)
            p_item.connect("activate", lambda m, p=prof: profile_manager.apply_profile(p))
            presets_menu.append(p_item)
        presets_item.set_submenu(presets_menu)
        menu.append(presets_item)

        # 4. Color Temp Submenu
        temp_item = Gtk.MenuItem(label="🌡 Color Temperatures")
        temp_menu = Gtk.Menu()
        for k in (2200, 2700, 3500, 4500, 5500, 6500):
            k_item = Gtk.MenuItem(label=f"{k}K")
            k_item.connect("activate", lambda m, val=k: control_engine.set_master_color_temp(val))
            temp_menu.append(k_item)
        temp_item.set_submenu(temp_menu)
        menu.append(temp_item)

        # 5. Night Mode Toggle
        night_item = Gtk.MenuItem(label="🌙 Toggle Night Mode")
        night_item.connect("activate", self._on_toggle_night)
        menu.append(night_item)

        # 6. Auto Mode Toggle & Resume
        is_auto = automation_engine.is_enabled()
        auto_label = "⚡ Auto Mode: ON" if is_auto else "⚡ Auto Mode: OFF"
        auto_item = Gtk.CheckMenuItem(label=auto_label)
        auto_item.set_active(is_auto)
        auto_item.connect("toggled", self._on_toggle_auto_mode)
        menu.append(auto_item)

        if is_auto and automation_engine.is_override_active():
            rem = automation_engine.get_override_remaining_seconds()
            mins = max(1, rem // 60)
            resume_item = Gtk.MenuItem(label=f"▶ Resume Auto ({mins}m paused)")
            resume_item.connect("activate", lambda m: automation_engine.clear_manual_override())
            menu.append(resume_item)

        menu.append(Gtk.SeparatorMenuItem())

        # 7. Refresh Displays
        refresh_item = Gtk.MenuItem(label="🔄 Refresh Displays")
        refresh_item.connect("activate", lambda m: monitor_service.discover_monitors())
        menu.append(refresh_item)

        # 8. Quit
        quit_item = Gtk.MenuItem(label="Quit LumaTray")
        quit_item.connect("activate", lambda m: self.on_quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _on_toggle_auto_mode(self, widget: Gtk.CheckMenuItem):
        new_active = widget.get_active()
        if new_active != automation_engine.is_enabled():
            automation_engine.set_enabled(new_active)

    def _on_automation_changed(self, **kwargs):
        if self._indicator:
            self._indicator.set_menu(self._build_menu())


    def _on_status_icon_activate(self, icon: Gtk.StatusIcon):
        """Left click on status icon: opens the quick panel as a popup in panel."""
        success, screen, area, orientation = icon.get_geometry()
        logger.info(f"StatusIcon activate (left-click)! success={success}, area=({area.x}, {area.y}, {area.width}, {area.height})")
        if success:
            center_x = area.x + area.width // 2
            center_y = area.y + area.height // 2
            self.on_toggle_quick_panel(
                center_x,
                center_y,
                anchor_area=(area.x, area.y, area.width, area.height, orientation),
            )
        else:
            self._on_menu_open_quick_panel()

    def _on_menu_open_quick_panel(self):
        """Open quick panel near pointer position as fallback."""
        display = Gdk.Display.get_default()
        seat = display.get_default_seat() if display else None
        if seat:
            pointer = seat.get_pointer()
            if pointer:
                _, px, py = pointer.get_position()
                self.on_toggle_quick_panel(px, py)
                return
        self.on_toggle_quick_panel(100, 100)

    def _on_status_icon_popup(self, icon: Gtk.StatusIcon, button: int, activate_time: int):
        """Right click context menu."""
        menu = self._build_menu()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)

    def _on_status_icon_scroll(self, icon: Gtk.StatusIcon, event: Gdk.EventScroll):
        """Mouse scroll wheel over tray icon."""
        step = config_store.get("slider_step", 5)
        delta = step if event.direction == Gdk.ScrollDirection.UP else -step
        self._adjust_wheel_brightness(delta)

    def _on_indicator_scroll(self, indicator, steps, direction):
        step = config_store.get("slider_step", 5)
        delta = step if direction == 0 else -step
        self._adjust_wheel_brightness(delta)

    def _adjust_wheel_brightness(self, delta: int):
        mons = monitor_service.get_monitors()
        if not mons:
            return
        cur_br = control_engine.get_state(mons[0].id).brightness
        new_br = max(1, min(100, cur_br + delta))
        control_engine.set_master_brightness(new_br)
        automation_engine.notify_manual_override()
        osd_manager.show("brightness", new_br)

    def _on_toggle_night(self, widget):
        mons = monitor_service.get_monitors()
        if not mons:
            return
        cur_k = control_engine.get_state(mons[0].id).color_temp
        target_prof = "daylight" if cur_k < 4500 else "night"
        profile_manager.apply_profile(target_prof)
