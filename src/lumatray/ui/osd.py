"""
Translucent On-Screen Display (OSD) overlay window for instant visual feedback.
"""

from __future__ import annotations

import logging
from gi.repository import Gdk, GLib, Gtk

from ..core.events import EventType, events

logger = logging.getLogger(__name__)


class OSDWindow(Gtk.Window):
    """Floating transparent OSD overlay window."""

    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)

        self.set_title("LumaTray OSD")
        self.set_role("osd")
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)

        # RGBA visual for transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)

        self.get_style_context().add_class("lumatray-osd")

        # Container
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.get_style_context().add_class("luma-osd-box")
        box.set_size_request(260, 110)

        # Header: Icon & Title
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.icon_label = Gtk.Label()
        self.icon_label.set_markup("<span font='22'>☀</span>")

        self.title_label = Gtk.Label(label="Brightness")
        self.title_label.get_style_context().add_class("luma-osd-title")
        self.title_label.set_xalign(0.0)

        self.value_label = Gtk.Label(label="100%")
        self.value_label.get_style_context().add_class("luma-osd-value")
        self.value_label.set_xalign(1.0)

        header.pack_start(self.icon_label, False, False, 0)
        header.pack_start(self.title_label, True, True, 0)
        header.pack_end(self.value_label, False, False, 0)
        box.pack_start(header, False, False, 0)

        # Progress / Level bar
        self.level_bar = Gtk.ProgressBar()
        self.level_bar.set_fraction(1.0)
        self.level_bar.set_size_request(-1, 8)
        box.pack_start(self.level_bar, False, False, 4)

        self.add(box)
        self._hide_timer_id: int | None = None

        # Subscribe to OSD events on GTK main thread
        events.subscribe(EventType.OSD_REQUESTED, self._on_osd_event, on_main_thread=True)

    def _on_osd_event(self, feature: str, value: int, label: str = "", duration_ms: int = 1500):
        if feature == "brightness":
            self.icon_label.set_markup("<span font='22'>☀</span>")
            self.title_label.set_text(label or "Brightness")
            self.value_label.set_text(f"{value}%")
            self.level_bar.set_fraction(max(0.0, min(1.0, value / 100.0)))
        elif feature == "contrast":
            self.icon_label.set_markup("<span font='22'>◑</span>")
            self.title_label.set_text(label or "Contrast")
            self.value_label.set_text(f"{value}%")
            self.level_bar.set_fraction(max(0.0, min(1.0, value / 100.0)))
        elif feature in ("kelvin", "color_temp"):
            self.icon_label.set_markup("<span font='22'>🌡</span>")
            self.title_label.set_text(label or "Color Temp")
            self.value_label.set_text(f"{value}K")
            # Map 1000K-10000K to 0.0-1.0
            frac = max(0.0, min(1.0, (value - 1000) / 9000.0))
            self.level_bar.set_fraction(frac)

        self._reposition()
        self.show_all()

        if self._hide_timer_id:
            GLib.source_remove(self._hide_timer_id)
        self._hide_timer_id = GLib.timeout_add(duration_ms, self._auto_hide)

    def _reposition(self):
        screen = self.get_screen()
        display = screen.get_display()
        seat = display.get_default_seat()
        pointer = seat.get_pointer() if seat else None
        if pointer:
            _, x, y = pointer.get_position()
            monitor = display.get_monitor_at_point(x, y)
        else:
            monitor = display.get_primary_monitor() or display.get_monitor(0)

        if monitor:
            geom = monitor.get_geometry()
            # Position at center horizontally, lower third vertically
            win_w, win_h = 280, 120
            pos_x = geom.x + (geom.width - win_w) // 2
            pos_y = geom.y + int(geom.height * 0.75) - win_h
            self.move(pos_x, pos_y)

    def _auto_hide(self) -> bool:
        self._hide_timer_id = None
        self.hide()
        return False
