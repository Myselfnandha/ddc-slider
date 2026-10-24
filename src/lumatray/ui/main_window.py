"""
Main application window providing 5 modular destinations:
Overview, Displays, Profiles, Automation, Settings and Diagnostics.
"""

from __future__ import annotations

import logging
from gi.repository import Gdk, Gtk

from .automation_view import AutomationView
from .displays_view import DisplaysView
from .overview_view import OverviewView
from .profiles_view import ProfilesView
from .settings_view import SettingsView
from ..storage.config_store import config_store

logger = logging.getLogger(__name__)


class MainWindow(Gtk.Window):
    """Full 5-destination Monitor Control Suite window."""

    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        self.set_title("LumaTray Monitor Control Suite")
        self.set_default_size(880, 620)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("lumatray-window")

        # HeaderBar
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("LumaTray")
        header.set_subtitle("Monitor Control Suite")
        header.get_style_context().add_class("luma-header")
        self.set_titlebar(header)

        # Main Layout
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root_box)

        # Stack & StackSwitcher
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)

        stack_switcher = Gtk.StackSwitcher()
        stack_switcher.set_stack(self.stack)
        header.set_custom_title(stack_switcher)

        # Destination 1: Overview
        self.overview_view = OverviewView()
        self.stack.add_titled(self.overview_view, "overview", "Overview")

        # Destination 2: Displays
        self.displays_view = DisplaysView()
        self.stack.add_titled(self.displays_view, "displays", "Displays")

        # Destination 3: Profiles
        self.profiles_view = ProfilesView()
        self.stack.add_titled(self.profiles_view, "profiles", "Profiles")

        # Destination 4: Automation
        self.automation_view = AutomationView()
        self.stack.add_titled(self.automation_view, "automation", "Automation")

        # Destination 5: Settings & Diagnostics
        self.settings_view = SettingsView()
        self.stack.add_titled(self.settings_view, "settings", "Settings & Diagnostics")

        root_box.pack_start(self.stack, True, True, 0)
        self.connect("delete-event", self._on_delete_event)

    def _on_delete_event(self, widget, event):
        # If close to tray is configured, hide instead of exiting
        if config_store.get("close_to_tray", True):
            self.hide()
            return True
        return False
