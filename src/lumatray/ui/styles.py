"""
Modern GTK3 styling and CSS theme provider for LumaTray.
"""

from __future__ import annotations

import logging
from gi.repository import Gdk, Gtk

logger = logging.getLogger(__name__)

LUMATRAY_CSS = """
/* Base application typography and surfaces */
window.lumatray-window,
window.lumatray-popup,
window.lumatray-osd {
    font-family: -apple-system, BlinkMacSystemFont, "Cantarell", "Inter", "Segoe UI", Roboto, sans-serif;
    color: #e6edf3;
}

window.lumatray-popup {
    background-color: transparent;
}

/* Main window background */
.lumatray-window {
    background-color: #0f141c;
}

/* Quick popup card container */
.lumatray-popup-box {
    background-color: rgba(22, 27, 34, 0.96);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    padding: 16px;
    box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6);
}

/* Cards & containers */
.luma-card {
    background-color: rgba(30, 38, 49, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 10px;
}

.luma-card:hover {
    border-color: rgba(99, 102, 241, 0.4);
}

/* Headerbar */
.luma-header {
    background: linear-gradient(180deg, #161b22 0%, #0f141c 100%);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    padding: 6px 12px;
}

/* Sidebar navigation */
.luma-sidebar {
    background-color: #121821;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.luma-nav-button {
    font-size: 13px;
    font-weight: 500;
    color: #8b949e;
    border-radius: 8px;
    padding: 8px 14px;
    margin: 3px 6px;
    background: transparent;
    border: none;
    box-shadow: none;
}

.luma-nav-button:hover {
    color: #ffffff;
    background-color: rgba(255, 255, 255, 0.06);
}

.luma-nav-button:checked,
.luma-nav-button.active {
    color: #ffffff;
    background-color: #6366f1;
    font-weight: 600;
}

/* Sliders / GtkScale */
scale.luma-scale trough {
    background-color: rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    min-height: 8px;
}

scale.luma-scale highlight {
    background: linear-gradient(90deg, #6366f1, #38bdf8);
    border-radius: 6px;
}

scale.luma-scale-temp highlight {
    background: linear-gradient(90deg, #f97316, #fbbf24, #93c5fd);
    border-radius: 6px;
}

scale.luma-scale slider {
    background-color: #ffffff;
    border: 2px solid #6366f1;
    border-radius: 50%;
    min-width: 18px;
    min-height: 18px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}

scale.luma-scale slider:hover {
    background-color: #f1f5f9;
}


/* Badges & Status Chips */
.luma-badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 12px;
    background-color: rgba(99, 102, 241, 0.2);
    color: #a5b4fc;
    border: 1px solid rgba(99, 102, 241, 0.3);
}

.luma-badge-success {
    background-color: rgba(34, 197, 94, 0.15);
    color: #4ade80;
    border-color: rgba(34, 197, 94, 0.3);
}

.luma-badge-warning {
    background-color: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border-color: rgba(245, 158, 11, 0.3);
}

/* Buttons */
.luma-btn-primary {
    background: linear-gradient(135deg, #6366f1, #4f46e5);
    color: #ffffff;
    font-weight: 600;
    border-radius: 8px;
    padding: 6px 14px;
    border: none;
}

.luma-btn-primary:hover {
    background: linear-gradient(135deg, #4f46e5, #4338ca);
}

.luma-btn-secondary {
    background-color: rgba(255, 255, 255, 0.08);
    color: #e6edf3;
    border-radius: 8px;
    padding: 6px 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
}

.luma-btn-secondary:hover {
    background-color: rgba(255, 255, 255, 0.14);
}

.luma-btn-auto-on {
    background: linear-gradient(135deg, #10b981, #059669);
    color: #ffffff;
    font-weight: 600;
    font-size: 11px;
    border-radius: 8px;
    padding: 4px 10px;
    border: none;
}

.luma-btn-auto-on:hover {
    background: linear-gradient(135deg, #059669, #047857);
}

.luma-btn-auto-off {
    background-color: rgba(255, 255, 255, 0.08);
    color: #94a3b8;
    font-weight: 500;
    font-size: 11px;
    border-radius: 8px;
    padding: 4px 10px;
    border: 1px solid rgba(255, 255, 255, 0.12);
}

.luma-btn-auto-off:hover {
    background-color: rgba(255, 255, 255, 0.14);
    color: #f1f5f9;
}

/* OSD Overlay */
.luma-osd-box {
    background-color: rgba(15, 20, 28, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 18px;
    padding: 22px 30px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7);
}

.luma-osd-title {
    font-size: 15px;
    font-weight: 600;
    color: #94a3b8;
}

.luma-osd-value {
    font-size: 26px;
    font-weight: 700;
    color: #ffffff;
}
"""


def apply_theme():
    """Apply LumaTray CSS theme to the default GTK screen."""
    try:
        screen = Gdk.Screen.get_default()
        if not screen:
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(LUMATRAY_CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
    except Exception as e:
        logger.error(f"Failed to apply GTK CSS styles: {e}")
