"""
Quick control panel: lightweight floating popup for everyday adjustments.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, List, Optional
from gi.repository import Gdk, GLib, Gtk

from ..core.events import EventType, events
from ..core.models import DisplayIdentity, Profile
from ..services.automation_engine import automation_engine
from ..services.control_engine import control_engine
from ..services.monitor_service import monitor_service
from ..services.profile_manager import profile_manager
from ..storage.config_store import config_store
from ..storage.profile_store import profile_store

logger = logging.getLogger(__name__)


class SliderCard(Gtk.Box):
    """A card containing Brightness, Contrast, and Color Temp sliders for one monitor or master."""

    def __init__(
        self,
        title: str,
        display_id: Optional[str] = None,
        is_master: bool = False,
        color_mode: str = "gamma",
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.display_id = display_id
        self.is_master = is_master
        self.get_style_context().add_class("luma-card")
        self._updating = False

        self._debounce_br: Optional[int] = None
        self._debounce_co: Optional[int] = None
        self._debounce_ct: Optional[int] = None

        # Title row
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{title}</b>")
        lbl.set_xalign(0.0)
        title_box.pack_start(lbl, True, True, 0)

        if not is_master and color_mode:
            mode_chip = Gtk.Label(label=color_mode)
            mode_chip.get_style_context().add_class("luma-badge")
            title_box.pack_end(mode_chip, False, False, 0)

        self.pack_start(title_box, False, False, 0)

        # 1. Brightness row
        self.br_scale, self.br_label = self._create_slider_row(
            "☀ Brightness", 0, 100, 50, "%", self._on_br_changed
        )

        # 2. Contrast row
        self.co_scale, self.co_label = self._create_slider_row(
            "◑ Contrast", 0, 100, 50, "%", self._on_co_changed
        )

        # 3. Color Temp row
        self.ct_scale, self.ct_label = self._create_slider_row(
            "🌡 Kelvin", 1500, 6500, 6500, "K", self._on_ct_changed, is_temp=True
        )

    def _create_slider_row(
        self, title: str, lower: int, upper: int, initial: int, unit: str, on_change: Callable, is_temp: bool = False
    ) -> tuple[Gtk.Scale, Gtk.Label]:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        t_lbl = Gtk.Label(label=title)
        t_lbl.set_xalign(0.0)
        t_lbl.get_style_context().add_class("luma-osd-title")

        val_lbl = Gtk.Label(label=f"{initial}{unit}")
        val_lbl.set_xalign(1.0)

        hdr.pack_start(t_lbl, True, True, 0)
        hdr.pack_end(val_lbl, False, False, 0)
        box.pack_start(hdr, False, False, 0)

        step = config_store.get("slider_step", 5)
        adj = Gtk.Adjustment(value=initial, lower=lower, upper=upper, step_increment=step, page_increment=step * 2)
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        scale.set_digits(0)
        scale.set_draw_value(False)
        scale.get_style_context().add_class("luma-scale")
        if is_temp:
            scale.get_style_context().add_class("luma-scale-temp")

        scale.connect("value-changed", lambda s: on_change(int(s.get_value()), val_lbl, unit))
        box.pack_start(scale, False, False, 0)
        self.pack_start(box, False, False, 0)
        return scale, val_lbl

    def _on_br_changed(self, val: int, label: Gtk.Label, unit: str):
        label.set_text(f"{val}{unit}")
        if self._updating:
            return
        if self._debounce_br:
            GLib.source_remove(self._debounce_br)
        self._debounce_br = GLib.timeout_add(120, self._apply_br, val)

    def _apply_br(self, val: int) -> bool:
        self._debounce_br = None
        if self.is_master:
            control_engine.set_master_brightness(val)
        elif self.display_id:
            control_engine.set_brightness(self.display_id, val)
        automation_engine.notify_manual_override()
        return False

    def _on_co_changed(self, val: int, label: Gtk.Label, unit: str):
        label.set_text(f"{val}{unit}")
        if self._updating:
            return
        if self._debounce_co:
            GLib.source_remove(self._debounce_co)
        self._debounce_co = GLib.timeout_add(120, self._apply_co, val)

    def _apply_co(self, val: int) -> bool:
        self._debounce_co = None
        if self.is_master:
            control_engine.set_master_contrast(val)
        elif self.display_id:
            control_engine.set_contrast(self.display_id, val)
        automation_engine.notify_manual_override()
        return False

    def _on_ct_changed(self, val: int, label: Gtk.Label, unit: str):
        label.set_text(f"{val}{unit}")
        if self._updating:
            return
        if self._debounce_ct:
            GLib.source_remove(self._debounce_ct)
        self._debounce_ct = GLib.timeout_add(120, self._apply_ct, val)

    def _apply_ct(self, val: int) -> bool:
        self._debounce_ct = None
        if self.is_master:
            control_engine.set_master_color_temp(val)
        elif self.display_id:
            control_engine.set_color_temp(self.display_id, val)
        automation_engine.notify_manual_override()
        return False

    def update_values(self, br: Optional[int] = None, co: Optional[int] = None, ct: Optional[int] = None):
        """Update slider positions programmatically without triggering write callbacks."""
        self._updating = True
        if br is not None:
            self.br_scale.set_value(br)
            self.br_label.set_text(f"{br}%")
        if co is not None:
            self.co_scale.set_value(co)
            self.co_label.set_text(f"{co}%")
        if ct is not None:
            self.ct_scale.set_value(ct)
            self.ct_label.set_text(f"{ct}K")
        self._updating = False


class QuickPanelWindow(Gtk.Window):
    """Floating quick panel popup."""

    def __init__(self, on_open_suite: Optional[Callable] = None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.on_open_suite = on_open_suite
        self.set_title("LumaTray Quick Panel")
        self.set_role("quick-panel")
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_gravity(Gdk.Gravity.NORTH_WEST)
        self.set_position(Gtk.WindowPosition.NONE)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.get_style_context().add_class("lumatray-popup")

        self._had_focus = False
        self._last_hide_time = 0.0
        self.connect("focus-in-event", self._on_focus_in)
        self.connect("focus-out-event", self._on_focus_out)
        self.connect("key-press-event", self._on_key_press)

        self._container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._container.get_style_context().add_class("lumatray-popup-box")
        self._container.set_size_request(340, -1)
        self.add(self._container)


        self._master_card: Optional[SliderCard] = None
        self._monitor_cards: Dict[str, SliderCard] = {}
        self._rebuild_ui()

        # Listen to external changes to update sliders
        events.subscribe(EventType.MONITORS_CHANGED, self._on_monitors_changed, on_main_thread=True)
        events.subscribe(EventType.PROFILE_APPLIED, self._on_profile_applied, on_main_thread=True)
        events.subscribe(EventType.OVERRIDE_CHANGED, self._on_override_changed, on_main_thread=True)
        events.subscribe(EventType.AUTOMATION_STATE_CHANGED, self._on_automation_changed, on_main_thread=True)

    def _rebuild_ui(self):
        # Clear container
        for child in self._container.get_children():
            self._container.remove(child)
        self._monitor_cards.clear()

        # 1. Header with title & Full Suite button
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title = Gtk.Label()
        title.set_markup("<b><span font='13'>LumaTray</span></b>")
        title.set_xalign(0.0)
        hdr.pack_start(title, True, True, 0)

        suite_btn = Gtk.Button(label="⚙ Full Suite")
        suite_btn.get_style_context().add_class("luma-btn-secondary")
        suite_btn.connect("clicked", self._on_suite_clicked)
        hdr.pack_end(suite_btn, False, False, 0)
        self._container.pack_start(hdr, False, False, 0)

        # 2. Automation status bar
        self.status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0.0)

        self.resume_btn = Gtk.Button(label="▶ Resume")
        self.resume_btn.get_style_context().add_class("luma-btn-secondary")
        self.resume_btn.set_no_show_all(True)
        self.resume_btn.connect("clicked", lambda b: automation_engine.clear_manual_override())

        self.auto_btn = Gtk.Button(label="⚡ Auto: ON")
        self.auto_btn.connect("clicked", self._on_auto_btn_clicked)

        self.status_bar.pack_start(self.status_label, True, True, 0)
        self.status_bar.pack_end(self.auto_btn, False, False, 0)
        self.status_bar.pack_end(self.resume_btn, False, False, 0)
        self._update_status_chip()
        self._container.pack_start(self.status_bar, False, False, 0)

        # 3. Master Controls Card
        self._master_card = SliderCard("🎛 All Displays", is_master=True)
        self._container.pack_start(self._master_card, False, False, 0)

        # 4. Per-Monitor Cards (Scrollable if many displays)
        monitors = monitor_service.get_monitors()
        if len(monitors) > 1:
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_max_content_height(280)
            scroll.set_propagate_natural_height(True)
            mon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

            for m in monitors:
                st = control_engine.get_state(m.id)
                card = SliderCard(m.name, display_id=m.id, is_master=False, color_mode=st.color_mode)
                card.update_values(br=st.brightness, co=st.contrast, ct=st.color_temp)
                self._monitor_cards[m.id] = card
                mon_box.pack_start(card, False, False, 0)

            scroll.add(mon_box)
            self._container.pack_start(scroll, True, True, 0)
        elif len(monitors) == 1:
            m = monitors[0]
            st = control_engine.get_state(m.id)
            self._master_card.update_values(br=st.brightness, co=st.contrast, ct=st.color_temp)

        # 5. Quick Preset Scenes Row
        preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for p in profile_store.list_all()[:4]:
            btn = Gtk.Button(label=p.name)
            btn.get_style_context().add_class("luma-btn-secondary")
            btn.connect("clicked", lambda b, prof=p: profile_manager.apply_profile(prof))
            preset_box.pack_start(btn, True, True, 0)
        self._container.pack_start(preset_box, False, False, 4)

    def _update_status_chip(self):
        is_auto = automation_engine.is_enabled()
        override = automation_engine.is_override_active()

        # Update toggle button styling & label
        ctx = self.auto_btn.get_style_context()
        if is_auto:
            self.auto_btn.set_label("⚡ Auto: ON")
            self.auto_btn.set_tooltip_text("Auto Mode is ON. Click to turn OFF.")
            ctx.remove_class("luma-btn-auto-off")
            ctx.add_class("luma-btn-auto-on")
        else:
            self.auto_btn.set_label("⚡ Auto: OFF")
            self.auto_btn.set_tooltip_text("Auto Mode is OFF. Click to turn ON.")
            ctx.remove_class("luma-btn-auto-on")
            ctx.add_class("luma-btn-auto-off")

        # Update status text and resume button
        if not is_auto:
            self.status_label.set_markup("<span foreground='#8b949e'><b>Auto Mode: OFF</b></span>")
            self.resume_btn.set_visible(False)
        elif override:
            rem = automation_engine.get_override_remaining_seconds()
            mins = max(1, rem // 60)
            self.status_label.set_markup(
                f"<span foreground='#fbbf24'><b>Manual ({mins}m left)</b></span>"
            )
            self.resume_btn.set_visible(True)
        else:
            self.status_label.set_markup("<span foreground='#4ade80'><b>Circadian Auto</b></span>")
            self.resume_btn.set_visible(False)

    def _on_auto_btn_clicked(self, button):
        automation_engine.toggle_auto_mode()

    def _on_automation_changed(self, **kwargs):
        self._update_status_chip()


    def _on_monitors_changed(self, **kwargs):
        self._rebuild_ui()
        self.show_all()

    def _on_profile_applied(self, profile: Profile):
        if self._master_card:
            self._master_card.update_values(
                br=profile.master_brightness,
                co=profile.master_contrast,
                ct=profile.master_color_temp,
            )
        for disp_id, card in self._monitor_cards.items():
            if disp_id in profile.monitors:
                m_st = profile.monitors[disp_id]
                card.update_values(
                    br=m_st.get("brightness"),
                    co=m_st.get("contrast"),
                    ct=m_st.get("color_temp"),
                )
        self._update_status_chip()

    def _on_override_changed(self, **kwargs):
        self._update_status_chip()

    def _on_suite_clicked(self, button):
        self.hide()
        if self.on_open_suite:
            self.on_open_suite()

    def hide(self):
        self._last_hide_time = time.time()
        self._had_focus = False
        super().hide()

    def toggle(self, x: int = 100, y: int = 100, anchor_area: Optional[tuple] = None):
        now = time.time()
        # Prevent bounce when clicking the tray icon while popup is open
        if now - self._last_hide_time < 0.25:
            return

        if self.is_visible():
            self.hide()
        else:
            self._had_focus = False
            self._container.show_all()
            self._update_status_chip()
            self._reposition(x, y, anchor_area)
            self.show()
            self.present()

    def _reposition(self, target_x: int, target_y: int, anchor_area: Optional[tuple] = None):
        screen = self.get_screen()
        display = screen.get_display()
        monitor = display.get_monitor_at_point(target_x, target_y) if display else None
        if not monitor and display:
            monitor = display.get_primary_monitor() or display.get_monitor(0)

        pref_size = self.get_preferred_size()[1]
        popup_width = max(340, pref_size.width)
        popup_height = max(300, pref_size.height)

        if monitor:
            wa = monitor.get_workarea()
            if anchor_area:
                ax, ay, aw, ah, orient = anchor_area
                center_x = ax + (aw // 2)
                center_y = ay + (ah // 2)

                if orient == Gtk.Orientation.HORIZONTAL:
                    # Panel is top or bottom
                    if ay < wa.y + (wa.height // 2):
                        # Top panel: place directly below panel
                        pos_y = ay + ah + 4
                    else:
                        # Bottom panel: place directly above panel
                        pos_y = ay - popup_height - 4
                    pos_x = center_x - (popup_width // 2)
                else:
                    # Panel is vertical (left or right)
                    if ax < wa.x + (wa.width // 2):
                        pos_x = ax + aw + 4
                    else:
                        pos_x = ax - popup_width - 4
                    pos_y = center_y - (popup_height // 2)
            else:
                pos_x = target_x - (popup_width // 2)
                if target_y < wa.y + (wa.height // 2):
                    pos_y = target_y + 4
                else:
                    pos_y = target_y - popup_height - 4

            # Ensure completely visible within monitor workarea
            pos_x = max(wa.x + 6, min(wa.x + wa.width - popup_width - 6, pos_x))
            pos_y = max(wa.y + 2, min(wa.y + wa.height - popup_height - 4, pos_y))
        else:
            pos_x, pos_y = target_x, target_y

        self.move(pos_x, pos_y)

    def _on_focus_in(self, widget, event):
        self._had_focus = True
        return False

    def _on_focus_out(self, widget, event):
        if self._had_focus:
            GLib.timeout_add(150, self._check_focus)
        return False

    def _check_focus(self):
        if not self.is_visible():
            return False
        if self._had_focus and not self.has_toplevel_focus():
            self.hide()
        return False

    def _on_key_press(self, widget, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_q):
            self.hide()
            return True
        return False

