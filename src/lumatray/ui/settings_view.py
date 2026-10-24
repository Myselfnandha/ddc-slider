"""
Settings and Diagnostics view: system health checks, latency benchmarks,
user preferences, and one-click diagnostic report export.
"""

from __future__ import annotations

import logging
from gi.repository import Gtk

from ..services.diagnostics import diagnostics_service
from ..storage.config_store import config_store

logger = logging.getLogger(__name__)


class SettingsView(Gtk.Box):
    """Destination 5: Settings and Diagnostics."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_border_width(16)
        self._build_ui()

    def _build_ui(self):
        # 1. Header & Diagnostic Export
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label()
        lbl.set_markup("<b><span font='16'>Settings &amp; System Diagnostics</span></b>")

        lbl.set_xalign(0.0)
        hdr.pack_start(lbl, True, True, 0)

        export_btn = Gtk.Button(label="📥 Export Diagnostic JSON")
        export_btn.get_style_context().add_class("luma-btn-primary")
        export_btn.connect("clicked", self._on_export_diagnostics)
        hdr.pack_end(export_btn, False, False, 0)

        bench_btn = Gtk.Button(label="⚡ Benchmark Latency")
        bench_btn.get_style_context().add_class("luma-btn-secondary")
        bench_btn.connect("clicked", self._on_benchmark_latency)
        hdr.pack_end(bench_btn, False, False, 0)

        self.pack_start(hdr, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        scroll.add(main_box)
        self.pack_start(scroll, True, True, 0)

        # 2. General Preferences Card
        pref_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pref_card.get_style_context().add_class("luma-card")
        p_title = Gtk.Label()
        p_title.set_markup("<b>Application Preferences</b>")
        p_title.set_xalign(0.0)
        pref_card.pack_start(p_title, False, False, 0)

        # Slider step
        step_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        step_lbl = Gtk.Label(label="Slider Step Increment:")
        step_lbl.set_xalign(0.0)
        step_combo = Gtk.ComboBoxText()
        for s in (1, 2, 5, 10):
            step_combo.append_text(f"{s}%")
        cur_step = config_store.get("slider_step", 5)
        step_combo.set_active({1: 0, 2: 1, 5: 2, 10: 3}.get(cur_step, 2))
        step_combo.connect("changed", lambda c: config_store.set("slider_step", [1, 2, 5, 10][c.get_active()]))
        step_row.pack_start(step_lbl, True, True, 0)
        step_row.pack_end(step_combo, False, False, 0)
        pref_card.pack_start(step_row, False, False, 0)

        # OSD toggle
        osd_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        osd_lbl = Gtk.Label(label="Show On-Screen Display (OSD) overlay on changes:")
        osd_lbl.set_xalign(0.0)
        osd_switch = Gtk.Switch()
        osd_switch.set_active(config_store.get("show_osd", True))
        osd_switch.connect("notify::active", lambda s, p: config_store.set("show_osd", s.get_active()))
        osd_row.pack_start(osd_lbl, True, True, 0)
        osd_row.pack_end(osd_switch, False, False, 0)
        pref_card.pack_start(osd_row, False, False, 0)

        main_box.pack_start(pref_card, False, False, 0)

        # 3. System Permissions & Health Card
        health_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        health_card.get_style_context().add_class("luma-card")
        h_title = Gtk.Label()
        h_title.set_markup("<b>Hardware Permissions &amp; Driver Status</b>")
        h_title.set_xalign(0.0)
        health_card.pack_start(h_title, False, False, 0)

        perms = diagnostics_service.check_permissions()
        grid = Gtk.Grid()
        grid.set_column_spacing(16)
        grid.set_row_spacing(6)

        perm_items = [
            ("User Account:", perms.get("user")),
            ("In 'i2c' Group:", "✔ Yes" if perms.get("in_i2c_group") else "✖ No (run: sudo usermod -aG i2c $USER)"),
            ("In 'video' Group:", "✔ Yes" if perms.get("in_video_group") else "✖ No"),
            ("I2C Bus Nodes:", f"{len(perms.get('i2c_devices', {}))} devices detected"),
            ("Backlight Nodes:", f"{len(perms.get('backlight_devices', {}))} devices detected"),
        ]
        for idx, (k, v) in enumerate(perm_items):
            grid.attach(Gtk.Label(label=k, xalign=0.0), 0, idx, 1, 1)
            grid.attach(Gtk.Label(label=v, xalign=0.0), 1, idx, 1, 1)

        health_card.pack_start(grid, False, False, 0)
        main_box.pack_start(health_card, False, False, 0)

        # 4. Helper Tools Status Card
        tools_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tools_card.get_style_context().add_class("luma-card")
        t_title = Gtk.Label()
        t_title.set_markup("<b>Installed Helper Utilities</b>")
        t_title.set_xalign(0.0)
        tools_card.pack_start(t_title, False, False, 0)

        tools = diagnostics_service.check_tools()
        t_grid = Gtk.Grid()
        t_grid.set_column_spacing(16)
        t_grid.set_row_spacing(6)
        for idx, (t_name, info) in enumerate(tools.items()):
            t_grid.attach(Gtk.Label(label=f"{t_name}:", xalign=0.0), 0, idx, 1, 1)
            status_text = f"Installed ({info.get('version') or info.get('path')})" if info.get("installed") else "Not Installed"
            t_grid.attach(Gtk.Label(label=status_text, xalign=0.0), 1, idx, 1, 1)

        tools_card.pack_start(t_grid, False, False, 0)
        main_box.pack_start(tools_card, False, False, 0)

        # 5. Hotkeys & Scripting Reference Card
        hk_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hk_card.get_style_context().add_class("luma-card")
        hk_title = Gtk.Label()
        hk_title.set_markup("<b>Desktop Keybinding &amp; CLI Reference</b>")

        hk_title.set_xalign(0.0)
        hk_card.pack_start(hk_title, False, False, 0)

        commands = [
            ("Toggle Quick Panel:", "lumatray --show"),
            ("Brightness Up 5%:", "lumatray --set brightness +5"),
            ("Brightness Down 5%:", "lumatray --set brightness -5"),
            ("Toggle Night Mode:", "lumatray --toggle-night"),
            ("Apply Scene:", "lumatray --apply-profile 'Movie'"),
        ]
        hk_grid = Gtk.Grid()
        hk_grid.set_column_spacing(16)
        hk_grid.set_row_spacing(6)
        for idx, (desc, cmd) in enumerate(commands):
            hk_grid.attach(Gtk.Label(label=desc, xalign=0.0), 0, idx, 1, 1)
            c_lbl = Gtk.Label(label=cmd, xalign=0.0)
            c_lbl.set_selectable(True)
            hk_grid.attach(c_lbl, 1, idx, 1, 1)

        hk_card.pack_start(hk_grid, False, False, 0)
        main_box.pack_start(hk_card, False, False, 0)

    def _on_benchmark_latency(self, button):
        latencies = diagnostics_service.benchmark_latency()
        lines = ["Hardware command round-trip latency benchmarks:\n"]
        for k, v in latencies.items():
            lines.append(f"• {k}: {v} ms")

        dialog = Gtk.MessageDialog(
            parent=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format="\n".join(lines),
        )
        dialog.run()
        dialog.destroy()

    def _on_export_diagnostics(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Export Diagnostic JSON Report",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Export", Gtk.ResponseType.OK)
        dialog.set_current_name("lumatray_diagnostics.json")
        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            out_path = diagnostics_service.export_report_to_file(filepath)
            diag_confirm = Gtk.MessageDialog(
                parent=self.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                message_format=f"Report exported successfully to:\n{out_path}",
            )
            diag_confirm.run()
            diag_confirm.destroy()
        dialog.destroy()
