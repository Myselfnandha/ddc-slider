"""
Overview view: primary control panel with master sliders, live monitor cards,
scene cards, and automation state.
"""

from __future__ import annotations

import logging
from gi.repository import Gtk

from ..core.events import EventType, events
from ..services.automation_engine import automation_engine
from ..services.control_engine import control_engine
from ..services.monitor_service import monitor_service
from ..services.profile_manager import profile_manager
from ..storage.profile_store import profile_store
from .quick_panel import SliderCard

logger = logging.getLogger(__name__)


class OverviewView(Gtk.Box):
    """Destination 1: Primary Overview."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_border_width(16)
        self._monitor_cards = {}
        self._master_card = None
        self._build_ui()

        events.subscribe(EventType.MONITORS_CHANGED, lambda **kw: self._rebuild(), on_main_thread=True)
        events.subscribe(EventType.OVERRIDE_CHANGED, lambda **kw: self._update_automation_status(), on_main_thread=True)

    def _build_ui(self):
        # 1. Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label()
        lbl.set_markup("<b><span font='16'>Monitor Control Center</span></b>")
        lbl.set_xalign(0.0)
        hdr.pack_start(lbl, True, True, 0)

        self.auto_badge = Gtk.Label()
        self._update_automation_status()
        hdr.pack_end(self.auto_badge, False, False, 0)
        self.pack_start(hdr, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll.add(self.content_box)
        self.pack_start(scroll, True, True, 0)

        self._rebuild()

    def _rebuild(self):
        for child in self.content_box.get_children():
            self.content_box.remove(child)
        self._monitor_cards.clear()

        # Master Controls
        self._master_card = SliderCard("🎛 Master Display Controls (All Displays)", is_master=True)
        self.content_box.pack_start(self._master_card, False, False, 0)

        # Quick Preset Scenes
        p_hdr = Gtk.Label()
        p_hdr.set_markup("<b>Quick Scenes</b>")
        p_hdr.set_xalign(0.0)
        self.content_box.pack_start(p_hdr, False, False, 2)

        preset_flow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for prof in profile_store.list_all()[:6]:
            btn = Gtk.Button(label=prof.name)
            btn.get_style_context().add_class("luma-btn-secondary")
            btn.connect("clicked", lambda b, p=prof: profile_manager.apply_profile(p))
            preset_flow.pack_start(btn, True, True, 0)
        self.content_box.pack_start(preset_flow, False, False, 0)

        # Per-Monitor Controls
        m_hdr = Gtk.Label()
        m_hdr.set_markup("<b>Connected Displays</b>")
        m_hdr.set_xalign(0.0)
        self.content_box.pack_start(m_hdr, False, False, 4)

        monitors = monitor_service.get_monitors()
        for m in monitors:
            st = control_engine.get_state(m.id)
            card = SliderCard(m.name, display_id=m.id, is_master=False, color_mode=st.color_mode)
            card.update_values(br=st.brightness, co=st.contrast, ct=st.color_temp)
            self._monitor_cards[m.id] = card
            self.content_box.pack_start(card, False, False, 0)

        self.content_box.show_all()

    def _update_automation_status(self):
        override = automation_engine.is_override_active()
        if override:
            rem = automation_engine.get_override_remaining_seconds()
            self.auto_badge.set_markup(
                f"<span foreground='#fbbf24'><b>Manual Override</b> ({rem // 60}m remaining)</span>"
            )
        else:
            self.auto_badge.set_markup("<span foreground='#4ade80'><b>Circadian Active</b></span>")

