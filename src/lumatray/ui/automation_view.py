"""
Smart Automation view: circadian schedules, ambient sensor adaptation, idle dimming,
and manual override policy configuration.
"""

from __future__ import annotations

import logging
from gi.repository import GLib, Gtk

from ..backends.ambient_light import ambient_backend
from ..core.events import EventType, events
from ..services.automation_engine import automation_engine
from ..storage.config_store import config_store

logger = logging.getLogger(__name__)


class AutomationView(Gtk.Box):
    """Destination 4: Smart Automation."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_border_width(16)
        self._build_ui()
        events.subscribe(EventType.OVERRIDE_CHANGED, lambda **kw: self._update_override_status(), on_main_thread=True)
        events.subscribe(EventType.AUTOMATION_STATE_CHANGED, self._on_automation_state_changed, on_main_thread=True)

    def _build_ui(self):
        # 1. Header & Quick Toggle
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label()
        lbl.set_markup("<b><span font='16'>Smart Automation Engine</span></b>")
        lbl.set_xalign(0.0)
        hdr.pack_start(lbl, True, True, 0)

        self.circadian_switch = Gtk.Switch()
        self.circadian_switch.set_active(config_store.get("circadian_enabled", True))
        self.circadian_switch.connect("notify::active", self._on_circadian_toggled)
        hdr.pack_end(self.circadian_switch, False, False, 0)

        en_lbl = Gtk.Label(label="Enable Circadian Automation:")
        hdr.pack_end(en_lbl, False, False, 0)
        self.pack_start(hdr, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        scroll.add(main_box)
        self.pack_start(scroll, True, True, 0)

        # 2. Manual Override Card
        override_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        override_card.get_style_context().add_class("luma-card")
        o_title = Gtk.Label()
        o_title.set_markup("<b>Manual Override &amp; Resume Policy</b>")
        o_title.set_xalign(0.0)
        override_card.pack_start(o_title, False, False, 0)

        o_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.override_status_lbl = Gtk.Label()
        self.override_status_lbl.set_xalign(0.0)
        self.override_status_lbl.get_style_context().add_class("luma-badge")

        self.resume_btn = Gtk.Button(label="▶ Resume Automated Schedule")
        self.resume_btn.get_style_context().add_class("luma-btn-primary")
        self.resume_btn.connect("clicked", lambda b: automation_engine.clear_manual_override())

        self._update_override_status()
        o_row.pack_start(self.override_status_lbl, True, True, 0)
        o_row.pack_end(self.resume_btn, False, False, 0)
        override_card.pack_start(o_row, False, False, 0)


        # Override timeout slider
        t_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        t_lbl = Gtk.Label(label="Pause Duration on Slider Adjustment:")
        t_lbl.set_xalign(0.0)
        cur_to = config_store.get("manual_override_timeout_minutes", 45)
        adj = Gtk.Adjustment(value=cur_to, lower=5, upper=180, step_increment=5, page_increment=15)
        self.timeout_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        self.timeout_scale.set_digits(0)
        self.timeout_scale.get_style_context().add_class("luma-scale")
        self.timeout_val_lbl = Gtk.Label(label=f"{cur_to} min")
        self.timeout_scale.connect("value-changed", self._on_timeout_changed)

        t_row.pack_start(t_lbl, False, False, 0)
        t_row.pack_start(self.timeout_scale, True, True, 0)
        t_row.pack_end(self.timeout_val_lbl, False, False, 0)
        override_card.pack_start(t_row, False, False, 0)
        main_box.pack_start(override_card, False, False, 0)

        # 3. Circadian Waypoints Card
        wp_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        wp_card.get_style_context().add_class("luma-card")
        wp_title = Gtk.Label()
        wp_title.set_markup("<b>Circadian Day / Night Waypoint Schedule (Cosine Interpolation)</b>")
        wp_title.set_xalign(0.0)
        wp_card.pack_start(wp_title, False, False, 0)

        # Waypoints table
        grid = Gtk.Grid()
        grid.set_column_spacing(16)
        grid.set_row_spacing(6)
        headers = ["Waypoint Scene", "Time", "Brightness", "Contrast", "Kelvin"]
        for c_idx, h in enumerate(headers):
            h_lbl = Gtk.Label()
            h_lbl.set_markup(f"<b>{h}</b>")
            h_lbl.set_xalign(0.0)
            grid.attach(h_lbl, c_idx, 0, 1, 1)

        waypoints = config_store.get("circadian_waypoints", [])
        for r_idx, wp in enumerate(waypoints, start=1):
            grid.attach(Gtk.Label(label=wp.get("name", ""), xalign=0.0), 0, r_idx, 1, 1)
            grid.attach(Gtk.Label(label=wp.get("time", ""), xalign=0.0), 1, r_idx, 1, 1)
            grid.attach(Gtk.Label(label=f"{wp.get('brightness', '')}%", xalign=0.0), 2, r_idx, 1, 1)
            grid.attach(Gtk.Label(label=f"{wp.get('contrast', '')}%", xalign=0.0), 3, r_idx, 1, 1)
            grid.attach(Gtk.Label(label=f"{wp.get('color_temp', '')}K", xalign=0.0), 4, r_idx, 1, 1)

        wp_card.pack_start(grid, False, False, 0)
        main_box.pack_start(wp_card, False, False, 0)

        # 4. Ambient Sensor Adaptation Card
        amb_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        amb_card.get_style_context().add_class("luma-card")
        a_title = Gtk.Label()
        a_title.set_markup("<b>Ambient Light Sensor Adaptation (Linux IIO)</b>")
        a_title.set_xalign(0.0)
        amb_card.pack_start(a_title, False, False, 0)

        amb_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        sensor_avail = ambient_backend.is_available()
        lux_val = ambient_backend.get_lux() if sensor_avail else None
        sensor_status = f"Sensor Active ({lux_val:.1f} Lux)" if (sensor_avail and lux_val is not None) else ("Sensor Detected" if sensor_avail else "No compatible IIO light sensor detected")
        status_lbl = Gtk.Label(label=sensor_status)
        status_lbl.set_xalign(0.0)
        amb_row.pack_start(status_lbl, True, True, 0)

        self.amb_switch = Gtk.Switch()
        self.amb_switch.set_active(config_store.get("ambient_sensor_enabled", False))
        self.amb_switch.set_sensitive(sensor_avail)
        self.amb_switch.connect("notify::active", self._on_ambient_toggled)
        amb_row.pack_end(self.amb_switch, False, False, 0)
        amb_card.pack_start(amb_row, False, False, 0)
        main_box.pack_start(amb_card, False, False, 0)

        # 5. Idle Dimming Card
        idle_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        idle_card.get_style_context().add_class("luma-card")
        id_title = Gtk.Label()
        id_title.set_markup("<b>Display Idle Dimming &amp; Power Saving</b>")

        id_title.set_xalign(0.0)
        idle_card.pack_start(id_title, False, False, 0)

        id_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        id_lbl = Gtk.Label(label="Automatically dim monitors when system is idle:")
        id_lbl.set_xalign(0.0)
        id_row.pack_start(id_lbl, True, True, 0)

        self.idle_switch = Gtk.Switch()
        self.idle_switch.set_active(config_store.get("idle_dimming_enabled", False))
        self.idle_switch.connect("notify::active", self._on_idle_toggled)
        id_row.pack_end(self.idle_switch, False, False, 0)
        idle_card.pack_start(id_row, False, False, 0)

        main_box.pack_start(idle_card, False, False, 0)

    def _update_override_status(self):
        override = automation_engine.is_override_active()
        if override:
            rem = automation_engine.get_override_remaining_seconds()
            self.override_status_lbl.set_markup(
                f"<span foreground='#fbbf24'><b>Manual Override Active</b> ({rem // 60}m {rem % 60}s remaining)</span>"
            )
            self.resume_btn.set_sensitive(True)
        else:
            self.override_status_lbl.set_markup(
                "<span foreground='#4ade80'><b>Automated Schedule Active</b></span>"
            )
            self.resume_btn.set_sensitive(False)


    def _on_circadian_toggled(self, switch, gparam):
        active = switch.get_active()
        if active != automation_engine.is_enabled():
            automation_engine.set_enabled(active)

    def _on_automation_state_changed(self, enabled: bool = True, **kwargs):
        if self.circadian_switch.get_active() != enabled:
            self.circadian_switch.set_active(enabled)

    def _on_ambient_toggled(self, switch, gparam):
        config_store.set("ambient_sensor_enabled", switch.get_active())
        automation_engine.evaluate_now()

    def _on_idle_toggled(self, switch, gparam):
        config_store.set("idle_dimming_enabled", switch.get_active())

    def _on_timeout_changed(self, scale):
        val = int(scale.get_value())
        self.timeout_val_lbl.set_text(f"{val} min")
        config_store.set("manual_override_timeout_minutes", val)
