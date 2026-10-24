"""
Displays and Advanced Controls view: hardware capability inspection, RGB gains,
color presets, input switching with safety warnings, and raw VCP diagnostic query.
"""

from __future__ import annotations

import logging
from typing import Optional
from gi.repository import Gtk

from ..backends.ddcutil_backend import ddc_backend
from ..core.capability_registry import capability_registry
from ..core.models import DisplayIdentity, DisplayType
from ..core.validation import COLOR_PRESETS, INPUT_SOURCES, is_destructive_vcp
from ..services.color_service import color_service
from ..services.monitor_service import monitor_service
from ..services.profile_manager import profile_manager

logger = logging.getLogger(__name__)


class DisplaysView(Gtk.Box):
    """Destination 2: Displays & Advanced Controls."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_border_width(16)
        self._build_ui()

    def _build_ui(self):
        # 1. Header & Display Selector
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label()
        lbl.set_markup("<b><span font='16'>Displays &amp; Hardware Capabilities</span></b>")

        lbl.set_xalign(0.0)
        hdr.pack_start(lbl, True, True, 0)

        refresh_btn = Gtk.Button(label="🔄 Re-probe Displays")
        refresh_btn.get_style_context().add_class("luma-btn-secondary")
        refresh_btn.connect("clicked", lambda b: self.refresh())
        hdr.pack_end(refresh_btn, False, False, 0)

        snapshot_btn = Gtk.Button(label="💾 Backup Settings")
        snapshot_btn.get_style_context().add_class("luma-btn-secondary")
        snapshot_btn.connect("clicked", self._on_backup_snapshot)
        hdr.pack_end(snapshot_btn, False, False, 0)
        self.pack_start(hdr, False, False, 0)

        # 2. Main content: selector and details
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)

        # Left list: connected displays
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-selected", self._on_display_selected)
        scroll_list = Gtk.ScrolledWindow()
        scroll_list.set_size_request(240, 420)
        scroll_list.add(self.list_box)
        content_box.pack_start(scroll_list, False, False, 0)

        # Right pane: details & controls notebook
        self.detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll_detail = Gtk.ScrolledWindow()
        scroll_detail.add(self.detail_box)
        content_box.pack_start(scroll_detail, True, True, 0)

        self.pack_start(content_box, True, True, 0)
        self.refresh()

    def refresh(self):
        # Clear list box
        for row in self.list_box.get_children():
            self.list_box.remove(row)

        monitors = monitor_service.get_monitors()
        for m in monitors:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_border_width(8)
            t_lbl = Gtk.Label()
            t_lbl.set_markup(f"<b>{m.name}</b>")
            t_lbl.set_xalign(0.0)

            sub_text = f"Connector: {m.connector_name or 'N/A'} • Bus: {m.bus}" if m.bus > 0 else "Internal Panel"
            s_lbl = Gtk.Label(label=sub_text)
            s_lbl.set_xalign(0.0)
            s_lbl.get_style_context().add_class("luma-osd-title")

            box.pack_start(t_lbl, False, False, 0)
            box.pack_start(s_lbl, False, False, 0)
            row.add(box)
            row.display_data = m
            self.list_box.add(row)

        self.list_box.show_all()
        # Select first display
        first_row = self.list_box.get_row_at_index(0)
        if first_row:
            self.list_box.select_row(first_row)

    def _on_display_selected(self, listbox, row):
        if not row:
            return
        disp: DisplayIdentity = getattr(row, "display_data", None)
        if not disp:
            return

        for child in self.detail_box.get_children():
            self.detail_box.remove(child)

        # Build display detail card
        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        info_card.get_style_context().add_class("luma-card")
        i_title = Gtk.Label()
        i_title.set_markup(f"<b><span font='14'>{disp.name}</span></b>")
        i_title.set_xalign(0.0)
        info_card.pack_start(i_title, False, False, 0)

        meta_grid = Gtk.Grid()
        meta_grid.set_column_spacing(16)
        meta_grid.set_row_spacing(4)

        labels = [
            ("Type:", disp.display_type.value),
            ("Device Node:", disp.device_path),
            ("Connector:", disp.connector_name or "N/A"),
            ("Manufacturer:", disp.manufacturer or "Unknown"),
            ("Model:", disp.model or "Unknown"),
            ("Serial Number:", disp.serial or "N/A"),
            ("Color Mode:", color_service.get_color_mode_for_display(disp)),
        ]
        for idx, (k, v) in enumerate(labels):
            k_lbl = Gtk.Label(label=k)
            k_lbl.set_xalign(0.0)
            v_lbl = Gtk.Label(label=str(v))
            v_lbl.set_xalign(0.0)
            meta_grid.attach(k_lbl, 0, idx, 1, 1)
            meta_grid.attach(v_lbl, 1, idx, 1, 1)
        info_card.pack_start(meta_grid, False, False, 0)
        self.detail_box.pack_start(info_card, False, False, 0)

        # Advanced Controls Card (if external DDC)
        if disp.display_type == DisplayType.EXTERNAL_DDC:
            caps = capability_registry.get_capabilities(disp)

            adv_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            adv_card.get_style_context().add_class("luma-card")
            adv_title = Gtk.Label()
            adv_title.set_markup("<b>Advanced Color & Input Controls</b>")
            adv_title.set_xalign(0.0)
            adv_card.pack_start(adv_title, False, False, 0)

            # RGB Gain Sliders (0x16 Red, 0x18 Green, 0x1A Blue)
            rgb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            rgb_hdr = Gtk.Label(label="Hardware RGB Gains:")
            rgb_hdr.set_xalign(0.0)
            rgb_box.pack_start(rgb_hdr, False, False, 0)

            for color_name, vcp_code in (("Red Gain", 0x16), ("Green Gain", 0x18), ("Blue Gain", 0x1A)):
                r_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                lbl_c = Gtk.Label(label=f"{color_name}:")
                lbl_c.set_size_request(85, -1)
                lbl_c.set_xalign(0.0)
                adj = Gtk.Adjustment(value=100, lower=0, upper=100, step_increment=1, page_increment=5)
                scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
                scale.set_digits(0)
                scale.get_style_context().add_class("luma-scale")
                scale.connect("value-changed", lambda s, code=vcp_code: ddc_backend.set_vcp(disp.bus, code, int(s.get_value())))
                r_row.pack_start(lbl_c, False, False, 0)
                r_row.pack_start(scale, True, True, 0)
                rgb_box.pack_start(r_row, False, False, 0)
            adv_card.pack_start(rgb_box, False, False, 0)

            # Color Presets (0x14)
            if caps.supports(0x14):
                preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                p_lbl = Gtk.Label(label="Hardware Color Preset (0x14):")
                p_lbl.set_xalign(0.0)
                combo = Gtk.ComboBoxText()
                feat_14 = caps.get_feature(0x14)
                valid_presets = feat_14.supported_values if (feat_14 and feat_14.supported_values) else COLOR_PRESETS
                preset_codes = []
                for p_code, p_name in valid_presets.items():
                    combo.append_text(f"{p_name} (0x{p_code:02x})")
                    preset_codes.append(p_code)
                combo.set_active(0)
                combo.connect("changed", lambda c: ddc_backend.set_vcp(disp.bus, 0x14, preset_codes[c.get_active()]))
                preset_row.pack_start(p_lbl, False, False, 0)
                preset_row.pack_start(combo, False, False, 0)
                adv_card.pack_start(preset_row, False, False, 0)

            # Input Switching (0x60) with Safety Warning
            input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            in_lbl = Gtk.Label(label="Input Source (0x60):")
            in_lbl.set_xalign(0.0)
            in_combo = Gtk.ComboBoxText()
            feat_60 = caps.get_feature(0x60)
            valid_inputs = feat_60.supported_values if (feat_60 and feat_60.supported_values) else INPUT_SOURCES
            input_codes = []
            for i_code, i_name in valid_inputs.items():
                in_combo.append_text(f"{i_name} (0x{i_code:02x})")
                input_codes.append(i_code)
            in_combo.set_active(0)

            switch_btn = Gtk.Button(label="Switch Input...")
            switch_btn.get_style_context().add_class("luma-btn-secondary")
            switch_btn.connect("clicked", lambda b: self._confirm_and_switch_input(disp, input_codes[in_combo.get_active()]))

            input_row.pack_start(in_lbl, False, False, 0)
            input_row.pack_start(in_combo, False, False, 0)
            input_row.pack_start(switch_btn, False, False, 0)
            adv_card.pack_start(input_row, False, False, 0)

            self.detail_box.pack_start(adv_card, False, False, 0)

            # Raw VCP Inspector Card
            raw_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            raw_card.get_style_context().add_class("luma-card")
            r_title = Gtk.Label()
            r_title.set_markup("<b>Raw VCP Feature Query (Diagnostic)</b>")
            r_title.set_xalign(0.0)
            raw_card.pack_start(r_title, False, False, 0)

            query_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            vcp_entry = Gtk.Entry()
            vcp_entry.set_placeholder_text("VCP Hex (e.g. 10 or 0x10)")
            q_btn = Gtk.Button(label="Get VCP Value")
            q_btn.get_style_context().add_class("luma-btn-secondary")
            q_result = Gtk.Label(label="")

            def _query_raw(b):
                txt = vcp_entry.get_text().strip()
                try:
                    code = int(txt, 16) if txt.startswith("0x") else int(txt, 16 if len(txt) == 2 else 10)
                    if is_destructive_vcp(code):
                        q_result.set_text("Blocked: Destructive VCP code")
                        return
                    val = ddc_backend.get_vcp(disp.bus, code)
                    q_result.set_text(f"Result: {val} (0x{val:02x})" if val is not None else "Failed / No Response")
                except Exception as e:
                    q_result.set_text(f"Error: {e}")

            q_btn.connect("clicked", _query_raw)
            query_box.pack_start(vcp_entry, False, False, 0)
            query_box.pack_start(q_btn, False, False, 0)
            query_box.pack_start(q_result, True, True, 0)
            raw_card.pack_start(query_box, False, False, 0)
            self.detail_box.pack_start(raw_card, False, False, 0)

        self.detail_box.show_all()

    def _confirm_and_switch_input(self, disp: DisplayIdentity, input_code: int):
        dialog = Gtk.MessageDialog(
            parent=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            message_format=f"Are you sure you want to switch input on '{disp.name}' to 0x{input_code:02x}?\n\nIf the selected input port has no active signal, the monitor may turn blank or enter power saving mode.",
        )
        resp = dialog.run()
        dialog.destroy()
        if resp == Gtk.ResponseType.OK:
            ddc_backend.set_vcp(disp.bus, 0x60, input_code, async_write=False)

    def _on_backup_snapshot(self, button):
        snapshot = profile_manager.capture_current_snapshot()
        dialog = Gtk.MessageDialog(
            parent=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format=f"Settings backup successfully saved!\nTimestamp: {snapshot.get('created_at')}",
        )
        dialog.run()
        dialog.destroy()
