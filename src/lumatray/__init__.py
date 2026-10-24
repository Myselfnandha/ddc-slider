"""
LumaTray — Next-Generation GTK3 Monitor Control Suite
Modular hardware control, color management, smart automation, multi-monitor profiles,
hotkeys, diagnostics, scripting, and desktop integration.
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

__version__ = "3.0.0"
__app_name__ = "lumatray"
__author__ = "Nandha"
