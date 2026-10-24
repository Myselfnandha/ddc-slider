"""
Profiles and Scenes view: manage, preview diffs, apply, create, import, and export scene profiles.
"""

from __future__ import annotations

import logging
from gi.repository import Gtk

from ..core.events import EventType, events
from ..core.models import Profile
from ..services.profile_manager import profile_manager
from ..storage.profile_store import profile_store

logger = logging.getLogger(__name__)


class ProfilesView(Gtk.Box):
    """Destination 3: Profiles and Scenes."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_border_width(16)
        self._build_ui()
        events.subscribe(EventType.PROFILE_APPLIED, lambda **kw: self.refresh(), on_main_thread=True)

    def _build_ui(self):
        # 1. Header & Actions
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label()
        lbl.set_markup("<b><span font='16'>Profiles &amp; Scenes</span></b>")

        lbl.set_xalign(0.0)
        hdr.pack_start(lbl, True, True, 0)

        new_btn = Gtk.Button(label="+ Save Current as Profile")
        new_btn.get_style_context().add_class("luma-btn-primary")
        new_btn.connect("clicked", self._on_save_current_as_profile)
        hdr.pack_end(new_btn, False, False, 0)

        import_btn = Gtk.Button(label="📥 Import JSON")
        import_btn.get_style_context().add_class("luma-btn-secondary")
        import_btn.connect("clicked", self._on_import_clicked)
        hdr.pack_end(import_btn, False, False, 0)

        restore_btn = Gtk.Button(label="↩ Restore Last Snapshot")
        restore_btn.get_style_context().add_class("luma-btn-secondary")
        restore_btn.connect("clicked", self._on_restore_snapshot)
        hdr.pack_end(restore_btn, False, False, 0)

        self.pack_start(hdr, False, False, 0)

        # 2. Profiles Flow / List
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.profile_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        scroll.add(self.profile_list_box)
        self.pack_start(scroll, True, True, 0)

        self.refresh()

    def refresh(self):
        for child in self.profile_list_box.get_children():
            self.profile_list_box.remove(child)

        profiles = profile_store.list_all()
        active_id = profile_manager.active_profile_id

        for prof in profiles:
            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            card.get_style_context().add_class("luma-card")

            # Left info box
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            t_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            t_lbl = Gtk.Label()
            t_lbl.set_markup(f"<b><span font='13'>{prof.name}</span></b>")
            t_lbl.set_xalign(0.0)
            t_box.pack_start(t_lbl, False, False, 0)

            if prof.is_system:
                badge = Gtk.Label(label="System")
                badge.get_style_context().add_class("luma-badge")
                t_box.pack_start(badge, False, False, 0)
            if prof.id == active_id:
                active_badge = Gtk.Label(label="Active")
                active_badge.get_style_context().add_class("luma-badge-success")
                t_box.pack_start(active_badge, False, False, 0)

            info_box.pack_start(t_box, False, False, 0)

            desc_lbl = Gtk.Label(label=prof.description or "Configured display settings scene")
            desc_lbl.set_xalign(0.0)
            desc_lbl.get_style_context().add_class("luma-osd-title")
            info_box.pack_start(desc_lbl, False, False, 0)

            val_summary = (
                f"Master: ☀ {prof.master_brightness}% • ◑ {prof.master_contrast}% • 🌡 {prof.master_color_temp}K"
            )
            val_lbl = Gtk.Label(label=val_summary)
            val_lbl.set_xalign(0.0)
            info_box.pack_start(val_lbl, False, False, 0)
            card.pack_start(info_box, True, True, 0)

            # Action buttons
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            diff_btn = Gtk.Button(label="Preview Diff")
            diff_btn.get_style_context().add_class("luma-btn-secondary")
            diff_btn.connect("clicked", lambda b, p=prof: self._preview_diff(p))
            btn_box.pack_start(diff_btn, False, False, 0)

            apply_btn = Gtk.Button(label="Apply Scene")
            apply_btn.get_style_context().add_class("luma-btn-primary")
            apply_btn.connect("clicked", lambda b, p=prof: profile_manager.apply_profile(p))
            btn_box.pack_start(apply_btn, False, False, 0)

            exp_btn = Gtk.Button(label="Export")
            exp_btn.get_style_context().add_class("luma-btn-secondary")
            exp_btn.connect("clicked", lambda b, p=prof: self._export_profile(p))
            btn_box.pack_start(exp_btn, False, False, 0)

            if not prof.is_system:
                del_btn = Gtk.Button(label="🗑")
                del_btn.get_style_context().add_class("luma-btn-secondary")
                del_btn.connect("clicked", lambda b, p_id=prof.id: self._delete_profile(p_id))
                btn_box.pack_start(del_btn, False, False, 0)

            card.pack_end(btn_box, False, False, 0)
            self.profile_list_box.pack_start(card, False, False, 0)

        self.profile_list_box.show_all()

    def _preview_diff(self, profile: Profile):
        diff = profile_manager.preview_profile_diff(profile)
        if not diff:
            msg = f"Profile '{profile.name}' is already identical to current display settings."
        else:
            lines = [f"Changes to apply for '{profile.name}':\n"]
            for disp_id, changes in diff.items():
                lines.append(f"• Display {disp_id}:")
                for feat, (cur, tgt) in changes.items():
                    lines.append(f"    - {feat}: {cur} -> {tgt}")
            msg = "\n".join(lines)

        dialog = Gtk.MessageDialog(
            parent=self.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format=msg,
        )
        dialog.run()
        dialog.destroy()

    def _on_save_current_as_profile(self, button):
        dialog = Gtk.Dialog(title="Save Current Settings as Profile", parent=self.get_toplevel(), flags=Gtk.DialogFlags.MODAL)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Profile Name (e.g. Late Coding)")
        desc_entry = Gtk.Entry()
        desc_entry.set_placeholder_text("Description")

        box.pack_start(Gtk.Label(label="Name:"), False, False, 0)
        box.pack_start(name_entry, False, False, 0)
        box.pack_start(Gtk.Label(label="Description:"), False, False, 0)
        box.pack_start(desc_entry, False, False, 0)
        dialog.show_all()

        resp = dialog.run()
        if resp == Gtk.ResponseType.OK and name_entry.get_text().strip():
            profile_manager.save_current_as_profile(
                name_entry.get_text().strip(),
                description=desc_entry.get_text().strip(),
            )
            self.refresh()
        dialog.destroy()

    def _delete_profile(self, profile_id: str):
        profile_store.delete(profile_id)
        self.refresh()

    def _export_profile(self, profile: Profile):
        dialog = Gtk.FileChooserDialog(
            title="Export Profile to JSON",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        dialog.set_current_name(f"{profile.id}.json")
        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            profile_store.export_profile_to_json(profile.id, filepath)
        dialog.destroy()

    def _on_import_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Import Profile from JSON",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            prof = profile_store.import_profile_from_json(filepath)
            if prof:
                self.refresh()
        dialog.destroy()

    def _on_restore_snapshot(self, button):
        if profile_manager.restore_last_snapshot():
            dialog = Gtk.MessageDialog(
                parent=self.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                message_format="Restored display settings from last safety snapshot.",
            )
            dialog.run()
            dialog.destroy()
        else:
            dialog = Gtk.MessageDialog(
                parent=self.get_toplevel(),
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                message_format="No previous snapshot available to restore.",
            )
            dialog.run()
            dialog.destroy()
