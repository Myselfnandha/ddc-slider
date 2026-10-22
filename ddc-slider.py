#!/usr/bin/env python3

"""
ddc-slider — Universal Multi-Monitor Brightness, Contrast & Color Temp Manager

GTK3 tray icon / standalone window to control internal and external monitor
brightness, contrast, and color temperature.

Features:
  - Supports ALL screens:
      * Internal laptop displays (sysfs backlight / brightnessctl / xrandr)
      * External DDC/CI monitors (via ddcutil over I2C)
      * External non-DDC screens (via xrandr software fallback)
  - Color temperature control per-monitor and globally via direct xrandr gamma
  - Live automatic display hotplug detection (HDMI / DP / USB-C plug & unplug)
  - Non-blocking async queue for DDC commands (eliminates slider lag and stutter)
  - State cache for instant startup (background hardware refresh)
  - Master controls to adjust all connected displays simultaneously
  - Tray icon with scroll-wheel support for quick brightness adjustments
  - Rich customizable presets (Daylight, Reading, Movie, Night Owl, Candlelight)
  - 1-Click Night Mode toggle directly from the tray
  - Quick Color Temperature presets submenu
  - Per-monitor dimming & reset actions
  - Full CLI interface (--get, --set, --temp, --toggle-night, --list, --reset)
  - Single-instance IPC: running ddc-slider again instantly toggles the popup
  - JSON configuration (~/.config/ddc-slider/config.json)

Requirements:
  - brightnessctl (for laptop internal screens)
  - ddcutil (for external DDC/CI screens)
  - xrandr (for monitor gamma / color temperature / output mapping)
  - python3-gi, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1 or gir1.2-appindicator3-0.1
  - User in 'i2c' group for DDC/CI: sudo usermod -aG i2c $USER
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import gi
gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, Gdk, GLib

import subprocess
import argparse
import dataclasses
import glob
import json
import os
import re
import sys
import signal
import threading
import time
import shutil
import functools
import math
import socket
import traceback
import datetime

APP_NAME = "ddc-slider"
APP_VERSION = "2.6.0-all-screens"

_script_dir = os.path.dirname(os.path.realpath(__file__))
_prefix_share = os.path.join(os.path.dirname(_script_dir), "share", APP_NAME)
for _vpath in [
    os.path.join(_script_dir, "release.txt"),
    os.path.join(_prefix_share, "release.txt"),
]:
    try:
        with open(_vpath) as _f:
            APP_VERSION = _f.read().strip()
            break
    except FileNotFoundError:
        continue

DEFAULT_CONFIG_DIR = os.path.expanduser(f"~/.config/{APP_NAME}")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, "config.json")
DEFAULT_STATE_PATH = os.path.join(DEFAULT_CONFIG_DIR, "state.json")

# ---------------------------------------------------------------------------
#  Internationalization — translations for UI strings
# ---------------------------------------------------------------------------

_TRANSLATIONS = {
    "en": {
        "brightness":        "☀ Brightness",
        "contrast":          "◑ Contrast",
        "all_monitors":      "🎛 All Displays",
        "color_temp":        "🌡 Color Temp",
        "tooltip":           "Display Brightness",
        "tooltip_multi":     "Display Brightness ({n} screens)",
        "resume_redshift":   "▶ Resume Redshift",
        "pause_redshift":    "⏸ Pause Redshift",
        "refresh_monitors":  "🔄 Refresh Displays",
        "quit":              "Quit",
        "brightness_slider": "☀ Brightness Slider",
        "window_title":      "Display Brightness & Color Temp",
        "night_mode":        "🌙 Toggle Night Mode",
        "daylight_mode":     "☀ Return to Daylight",
        "reset_all":         "🔄 Reset All to 100%",
        "quick_temps":       "🌡 Color Temp Presets",
        "screen_actions":    "🖥 Display Actions",
        "edit_config":       "⚙ Edit Settings",
    },
    "es": {
        "brightness":        "☀ Brillo",
        "contrast":          "◑ Contraste",
        "all_monitors":      "🎛 Todas las Pantallas",
        "color_temp":        "🌡 Temp. Color",
        "tooltip":           "Brillo de Pantalla",
        "tooltip_multi":     "Brillo ({n} pantallas)",
        "resume_redshift":   "▶ Reanudar Redshift",
        "pause_redshift":    "⏸ Pausar Redshift",
        "refresh_monitors":  "🔄 Actualizar Pantallas",
        "quit":              "Salir",
        "brightness_slider": "☀ Control de Brillo",
        "window_title":      "Brillo y Temperatura de Pantalla",
        "night_mode":        "🌙 Modo Noche",
        "daylight_mode":     "☀ Modo Día",
        "reset_all":         "🔄 Restablecer Todo",
        "quick_temps":       "🌡 Temperaturas",
        "screen_actions":    "🖥 Acciones",
        "edit_config":       "⚙ Ajustes",
    },
    "de": {
        "brightness":        "☀ Helligkeit",
        "contrast":          "◑ Kontrast",
        "all_monitors":      "🎛 Alle Bildschirme",
        "color_temp":        "🌡 Farbtemperatur",
        "tooltip":           "Bildschirmhelligkeit",
        "tooltip_multi":     "Helligkeit ({n} Bildschirme)",
        "resume_redshift":   "▶ Redshift fortsetzen",
        "pause_redshift":    "⏸ Redshift pausieren",
        "refresh_monitors":  "🔄 Bildschirme aktualisieren",
        "quit":              "Beenden",
        "brightness_slider": "☀ Helligkeitsregler",
        "window_title":      "Helligkeit & Farbtemperatur",
        "night_mode":        "🌙 Nachtmodus umschalten",
        "daylight_mode":     "☀ Tagmodus",
        "reset_all":         "🔄 Alle zurücksetzen",
        "quick_temps":       "🌡 Farbtemperatur-Voreinstellungen",
        "screen_actions":    "🖥 Bildschirm-Aktionen",
        "edit_config":       "⚙ Einstellungen bearbeiten",
    },
    "fr": {
        "brightness":        "☀ Luminosité",
        "contrast":          "◑ Contraste",
        "all_monitors":      "🎛 Tous les Écrans",
        "color_temp":        "🌡 Temp. Couleur",
        "tooltip":           "Luminosité de l'écran",
        "tooltip_multi":     "Luminosité ({n} écrans)",
        "resume_redshift":   "▶ Reprendre Redshift",
        "pause_redshift":    "⏸ Pause Redshift",
        "refresh_monitors":  "🔄 Actualiser les Écrans",
        "quit":              "Quitter",
        "brightness_slider": "☀ Contrôle Luminosité",
        "window_title":      "Luminosité & Température",
        "night_mode":        "🌙 Mode Nuit",
        "daylight_mode":     "☀ Mode Jour",
        "reset_all":         "🔄 Tout Réinitialiser",
        "quick_temps":       "🌡 Préréglages Température",
        "screen_actions":    "🖥 Actions d'Écran",
        "edit_config":       "⚙ Modifier Paramètres",
    }
}


def _detect_lang() -> str:
    lang = os.environ.get("LC_MESSAGES", os.environ.get("LANG", "en"))
    code = lang.split(".")[0]
    if code in _TRANSLATIONS:
        return code
    prefix = code.split("_")[0]
    if prefix in _TRANSLATIONS:
        return prefix
    return "en"


_LANG = _detect_lang()
_STRINGS = _TRANSLATIONS.get(_LANG, _TRANSLATIONS["en"])


def _(key: str, **kwargs) -> str:
    s = _STRINGS.get(key) or _TRANSLATIONS["en"].get(key, key)
    if kwargs:
        s = s.format(**kwargs)
    return s


DEFAULT_CONFIG = {
    "scroll_step": 3,
    "include_internal_display": True,
    "show_contrast_slider": True,
    "show_color_temp_slider": True,
    "color_temp_min": 2200,
    "color_temp_max": 6500,
    "night_mode_temp": 2700,
    "night_mode_brightness": 35,
    "night_mode_contrast": 50,
    "auto_schedule_enabled": True,
    "day_time": "07:00",
    "night_time": "19:00",
    "day_mode_brightness": 100,
    "day_mode_contrast": 75,
    "day_mode_temp": 6500,
    "smooth_transition": True,
    "transition_duration_sec": 3.0,
    "schedule_notifications": True,
    "presets": [
        {"name": "☀ Daylight", "brightness": 100, "contrast": 75, "color_temp": 6500},
        {"name": "📖 Reading", "brightness": 75, "contrast": 50, "color_temp": 5000},
        {"name": "🎬 Movie", "brightness": 45, "contrast": 60, "color_temp": 3500},
        {"name": "🌙 Night Owl", "brightness": 25, "contrast": 45, "color_temp": 2700},
        {"name": "🕯 Candlelight", "brightness": 15, "contrast": 40, "color_temp": 2200},
    ],
    "custom_display_names": {},
}

DEFAULT_MIN = 0
DEFAULT_MAX = 100
DEFAULT_STEP = 1
DEFAULT_SCROLL_STEP = 3
VCP_BRIGHTNESS = 0x10
VCP_CONTRAST = 0x12
STATE_MAX_AGE = 86400

# Color temperature constants
COLOR_TEMP_MIN = 2200
COLOR_TEMP_MAX = 6500
COLOR_TEMP_STEP = 100
COLOR_TEMP_NEUTRAL = 6500
COLOR_TEMP_MARKS = [2200, 2700, 3500, 4500, 5500, 6500]


def _get_icon_path(icon_style: str | None = None) -> str:
    """Resolve the tray icon path, supporting 'light', 'dark', or auto-detect."""
    if icon_style is None or icon_style == "auto":
        settings = Gtk.Settings.get_default()
        theme_name = settings.get_property("gtk-theme-name").lower() if settings else ""
        icon_file = "ddc-slider-light.svg" if "dark" in theme_name else "ddc-slider.svg"
    elif icon_style == "light":
        icon_file = "ddc-slider-light.svg"
    else:
        icon_file = "ddc-slider.svg"

    candidates = [
        os.path.join(_script_dir, "images", icon_file),
        os.path.join(_prefix_share, "images", icon_file),
        f"/usr/local/share/ddc-slider/images/{icon_file}",
        f"/usr/share/ddc-slider/images/{icon_file}",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    fallback = os.path.join(_script_dir, "images", "ddc-slider.svg")
    return fallback if os.path.exists(fallback) else candidates[0]


def get_socket_path() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return os.path.join(runtime_dir, f"{APP_NAME}-{os.getuid()}.sock")


def send_ipc_message(msg: bytes) -> bool:
    """Send an arbitrary IPC command string to the running ddc-slider daemon."""
    sock_path = get_socket_path()
    if not os.path.exists(sock_path):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.5)
        s.connect(sock_path)
        s.sendall(msg)
        s.close()
        return True
    except Exception:
        try:
            os.remove(sock_path)
        except OSError:
            pass
        return False


def send_toggle_to_running_instance() -> bool:
    """Check if ddc-slider is already running; if so, send toggle message and return True."""
    return send_ipc_message(b"toggle\n")


def send_desktop_notification(title: str, message: str, icon: str = "display-brightness"):
    """Send a non-blocking desktop notification via notify-send."""
    try:
        subprocess.Popen([
            "notify-send",
            "-a", APP_NAME,
            "-i", icon,
            title,
            message
        ])
    except Exception:
        pass


def save_config_file(cfg: dict, path: str = DEFAULT_CONFIG_PATH):
    """Safely persist config dictionary to JSON disk file."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[{APP_NAME}] Warning: failed to save config to {path}: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
#  Monitor Representation
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class MonitorInfo:
    bus: int               # I2C bus number (>0) or virtual id (<0)
    device: str            # "/dev/i2c-X" or sysfs backlight path
    name: str              # Friendly display name
    brightness: object     # DDCController, BacklightController, or XRandrBrightnessController
    contrast: object       # DDCController or SoftwareContrastController
    output_name: str | None = None   # X randr output name, e.g. "eDP-1", "HDMI-1"
    crtc_index: int | None = None    # X randr CRTC index
    is_internal: bool = False
    current_brightness: int = 50
    current_contrast: int = 50
    current_color_temp: int = COLOR_TEMP_NEUTRAL


# ---------------------------------------------------------------------------
#  Backlight Controller for Internal Laptop Displays
# ---------------------------------------------------------------------------

class BacklightController:
    """Controls laptop internal screen backlight using sysfs and brightnessctl."""

    def __init__(self, backlight_path: str, output_name: str | None = None):
        self.backlight_path = backlight_path
        self.output_name = output_name
        self.max_brightness = 100
        if self.backlight_path and os.path.isdir(self.backlight_path):
            try:
                with open(os.path.join(self.backlight_path, "max_brightness")) as f:
                    self.max_brightness = max(1, int(f.read().strip()))
            except Exception:
                pass
        self._last_val = 100

    def get_value(self) -> int | None:
        if self.backlight_path and os.path.isdir(self.backlight_path):
            try:
                with open(os.path.join(self.backlight_path, "brightness")) as f:
                    cur = int(f.read().strip())
                val = max(1, min(100, round((cur / self.max_brightness) * 100)))
                self._last_val = val
                return val
            except Exception:
                pass

        try:
            res = subprocess.run(["brightnessctl", "-m"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().splitlines()[0].split(",")
                if len(parts) >= 4 and "%" in parts[3]:
                    val = int(parts[3].replace("%", ""))
                    self._last_val = val
                    return val
        except Exception:
            pass

        return self._last_val

    def set_value(self, value: int) -> bool:
        value = max(1, min(100, int(value)))
        self._last_val = value

        # 1. Primary: brightnessctl
        try:
            res = subprocess.run(["brightnessctl", "set", f"{value}%"],
                                 capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True
        except Exception:
            pass

        # 2. Sysfs direct write
        if self.backlight_path and os.path.isdir(self.backlight_path):
            try:
                raw_target = int(round((value / 100.0) * self.max_brightness))
                with open(os.path.join(self.backlight_path, "brightness"), "w") as f:
                    f.write(str(raw_target))
                return True
            except Exception:
                pass

        # 3. xrandr software brightness
        if self.output_name:
            try:
                frac = round(value / 100.0, 2)
                res = subprocess.run(["xrandr", "--output", self.output_name, "--brightness", str(frac)],
                                     capture_output=True, text=True, timeout=5)
                return res.returncode == 0
            except Exception:
                pass

        return False


class SoftwareContrastController:
    """Controls contrast/gamma for internal laptop screens and software-controlled screens."""

    def __init__(self, output_name: str | None = None):
        self.output_name = output_name
        self._value = 50

    def get_value(self) -> int | None:
        return self._value

    def set_value(self, value: int) -> bool:
        self._value = max(0, min(100, int(value)))
        return True


class XRandrBrightnessController:
    """Fallback controller for external displays without DDC, using xrandr --brightness."""

    def __init__(self, output_name: str):
        self.output_name = output_name
        self._value = 100

    def get_value(self) -> int | None:
        return self._value

    def set_value(self, value: int) -> bool:
        self._value = max(10, min(100, int(value)))
        frac = round(self._value / 100.0, 2)
        try:
            res = subprocess.run(["xrandr", "--output", self.output_name, "--brightness", str(frac)],
                                 capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False


# ---------------------------------------------------------------------------
#  Color temperature calculation & Per-output mapping
# ---------------------------------------------------------------------------

def kelvin_to_rgb(kelvin: int) -> tuple[float, float, float]:
    """Convert color temperature in Kelvin (1000K-10000K) to normalized RGB multipliers (0.0 - 1.0).
    Neutral daylight (6500K) maps to (1.0, 1.0, 1.0)."""
    kelvin = max(1000, min(10000, int(kelvin)))
    temp = kelvin / 100.0

    # Red
    if temp <= 66:
        r = 255.0
    else:
        r = 329.698727446 * ((temp - 60.0) ** -0.1332047592)
    r = max(0.0, min(255.0, r))

    # Green
    if temp <= 66:
        g = 99.4708025861 * math.log(max(1.0, temp)) - 161.1195681661
    else:
        g = 288.1221695283 * ((temp - 60.0) ** -0.0755148492)
    g = max(0.0, min(255.0, g))

    # Blue
    if temp >= 66:
        b = 255.0
    elif temp <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(max(1.0, temp - 10.0)) - 305.0447927307
    b = max(0.0, min(255.0, b))

    # Reference at 6500K: r=255.0, g≈254.18, b≈249.98
    r_factor = max(0.0, min(1.0, r / 255.0))
    g_factor = max(0.0, min(1.0, g / 254.18))
    b_factor = max(0.0, min(1.0, b / 249.98))
    return round(r_factor, 3), round(g_factor, 3), round(b_factor, 3)


def _get_drm_connector_for_bus(bus: int) -> str | None:
    """Find the DRM connector name (e.g. 'DP-1', 'HDMI-A-1') that owns an I2C bus."""
    try:
        entries = os.listdir("/sys/class/drm")
    except OSError:
        return None
    for entry in entries:
        if not re.match(r"^card\d+-", entry):
            continue
        for sub in ("ddc", "i2c-adapter"):
            path = f"/sys/class/drm/{entry}/{sub}"
            try:
                target = os.readlink(path)
            except OSError:
                try:
                    inner = os.listdir(path)
                except OSError:
                    continue
                for name in inner:
                    m = re.match(r"^i2c-(\d+)$", name)
                    if m and int(m.group(1)) == bus:
                        return entry.split("-", 1)[1]
                continue
            m = re.search(r"i2c-(\d+)", target)
            if m and int(m.group(1)) == bus:
                return entry.split("-", 1)[1]
    return None


def _xrandr_outputs() -> dict[str, int | None]:
    """Parse xrandr for currently connected output names and their CRTC indices."""
    result = {}
    try:
        proc = subprocess.run(
            ["xrandr", "--verbose"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            return result
        current_output = None
        for line in proc.stdout.splitlines():
            m_out = re.match(r"^(\S+)\s+connected", line)
            if m_out:
                current_output = m_out.group(1)
                result[current_output] = None
                continue
            if re.match(r"^\S+\s+(disconnected|connected)", line):
                current_output = None
                continue
            if current_output and result.get(current_output) is None:
                m_crtc = re.search(r"CRTC:\s*(\d+)", line)
                if m_crtc:
                    result[current_output] = int(m_crtc.group(1))
    except Exception as e:
        print(f"[{APP_NAME}] Error querying xrandr: {e}", file=sys.stderr)
    return result


def _match_xrandr_name(connector: str, xrandr_names: list[str]) -> str | None:
    if not connector:
        return None
    if connector in xrandr_names:
        return connector
    stripped = re.sub(r"-[A-Z]-(\d+)$", r"-\g<1>", connector)
    if stripped in xrandr_names:
        return stripped
    low = connector.lower()
    for name in xrandr_names:
        if name.lower() == low:
            return name
    return None


def resolve_output_for_bus(bus: int) -> tuple[str | None, int | None]:
    connector = _get_drm_connector_for_bus(bus)
    outs = _xrandr_outputs()
    if connector is None:
        external_outs = [k for k in outs.keys() if not re.match(r'^(eDP|LVDS|DSI)', k, re.IGNORECASE)]
        if len(external_outs) == 1:
            out = external_outs[0]
            return out, outs.get(out)
        return None, None
    if not outs:
        return connector, None
    matched = _match_xrandr_name(connector, list(outs.keys()))
    if matched is None:
        return connector, None
    return matched, outs.get(matched)


# ---------------------------------------------------------------------------
#  Monitor detection: Internal Displays + External DDC/CI + Hotplug
# ---------------------------------------------------------------------------

def detect_internal_monitors() -> list[MonitorInfo]:
    """Detect internal laptop screens via /sys/class/backlight and xrandr."""
    monitors = []
    backlights = sorted(glob.glob("/sys/class/backlight/*"))
    outs = _xrandr_outputs()

    internal_names = [name for name in outs.keys() if re.match(r'^(eDP|LVDS|DSI)', name, re.IGNORECASE)]

    if backlights:
        for idx, bl_path in enumerate(backlights):
            out_name = internal_names[idx] if idx < len(internal_names) else (internal_names[0] if internal_names else None)
            crtc_idx = outs.get(out_name) if out_name else None
            friendly_name = f"Laptop ({out_name})" if out_name else "Laptop Display"
            monitors.append(MonitorInfo(
                bus=-(idx + 1),
                device=bl_path,
                name=friendly_name,
                brightness=BacklightController(bl_path, out_name),
                contrast=SoftwareContrastController(out_name),
                output_name=out_name,
                crtc_index=crtc_idx,
                is_internal=True
            ))
    elif internal_names:
        for idx, out_name in enumerate(internal_names):
            crtc_idx = outs.get(out_name)
            monitors.append(MonitorInfo(
                bus=-(idx + 1),
                device=out_name,
                name=f"Laptop ({out_name})",
                brightness=BacklightController("", out_name),
                contrast=SoftwareContrastController(out_name),
                output_name=out_name,
                crtc_index=crtc_idx,
                is_internal=True
            ))
    return monitors


def detect_monitors() -> list[tuple[int, str]]:
    """Probe for external DDC-capable monitors via ddcutil detect."""
    monitors = []
    try:
        result = subprocess.run(
            ["ddcutil", "detect", "--brief"],
            capture_output=True, text=True, timeout=10
        )
        bus = None
        name = ""
        valid = False
        for line in result.stdout.splitlines():
            if re.match(r'^Display\s+\d+', line):
                if bus is not None and valid:
                    monitors.append((bus, name))
                bus = None
                name = ""
                valid = True
            elif re.match(r'^Invalid display', line):
                if bus is not None and valid:
                    monitors.append((bus, name))
                bus = None
                name = ""
                valid = False
            m = re.search(r'I2C bus:\s*/dev/i2c-(\d+)', line)
            if m:
                bus = int(m.group(1))
            m = re.search(r'(?:Model|Monitor):\s*(.+)', line)
            if m:
                full_model = m.group(1).strip()
                if ":" in full_model:
                    parts = [p.strip() for p in full_model.split(":") if p.strip()]
                    name = parts[1] if len(parts) >= 2 and parts[1] else (parts[0] if parts else full_model)
                else:
                    name = full_model.split()[0] if full_model else ""
        if bus is not None and valid:
            monitors.append((bus, name))
    except Exception as e:
        print(f"[{APP_NAME}] Error probing DDC monitors: {e}", file=sys.stderr)
    return monitors


def probe_all_monitors(vcp_brightness: int = VCP_BRIGHTNESS,
                       vcp_contrast: int = VCP_CONTRAST,
                       include_internal: bool = True,
                       cached_state: list[dict] | None = None) -> list[MonitorInfo]:
    """Unified full hardware probe: detects all internal, DDC external, and software displays."""
    outs = _xrandr_outputs()
    claimed_outputs: set[str] = set()
    monitors: list[MonitorInfo] = []

    # 1. Internal displays
    if include_internal:
        for m in detect_internal_monitors():
            monitors.append(m)
            if m.output_name:
                claimed_outputs.add(m.output_name)

    # 2. External DDC/CI displays
    detected_ddc = detect_monitors()
    for bus, name in detected_ddc:
        device = f"/dev/i2c-{bus}"
        output_name, crtc_index = resolve_output_for_bus(bus)
        if output_name:
            claimed_outputs.add(output_name)
        label_name = name or (f"Display ({output_name})" if output_name else f"Display (bus {bus})")
        monitors.append(MonitorInfo(
            bus=bus,
            device=device,
            name=label_name,
            brightness=DDCController(bus, vcp_brightness),
            contrast=DDCController(bus, vcp_contrast),
            output_name=output_name,
            crtc_index=crtc_index,
            is_internal=False,
        ))

    # 3. External displays detected by xrandr but without DDC response
    external_outs = [name for name in outs.keys() if not re.match(r'^(eDP|LVDS|DSI)', name, re.IGNORECASE)]
    for idx, out_name in enumerate(external_outs):
        if out_name not in claimed_outputs:
            claimed_outputs.add(out_name)
            vbus = -10 - idx
            crtc_index = outs.get(out_name)
            monitors.append(MonitorInfo(
                bus=vbus,
                device=out_name,
                name=f"Display ({out_name})",
                brightness=XRandrBrightnessController(out_name),
                contrast=SoftwareContrastController(out_name),
                output_name=out_name,
                crtc_index=crtc_index,
                is_internal=False,
            ))

    # 4. Restore settings from cached state if available
    if cached_state:
        bus_map = {e.get("bus"): e for e in cached_state if "bus" in e}
        out_map = {e.get("output_name"): e for e in cached_state if e.get("output_name")}
        for m in monitors:
            entry = bus_map.get(m.bus) or out_map.get(m.output_name)
            if entry:
                m.current_brightness = entry.get("brightness", m.current_brightness)
                m.current_contrast = entry.get("contrast", m.current_contrast)
                m.current_color_temp = entry.get("color_temp", m.current_color_temp)

    return monitors


def build_monitors(detected: list[tuple[int, str]], vcp_brightness: int,
                   vcp_contrast: int, include_internal: bool = True) -> list[MonitorInfo]:
    """Compatibility wrapper for build_monitors."""
    return probe_all_monitors(vcp_brightness, vcp_contrast, include_internal=include_internal)


def fast_build_from_cache(cached: list[dict], vcp_brightness: int,
                          vcp_contrast: int, include_internal: bool = True) -> list[MonitorInfo] | None:
    """Build monitor list from cached state if all cached monitors match currently connected outputs."""
    outs = _xrandr_outputs()
    if not outs:
        return None
    connected_outputs = set(outs.keys())
    monitors: list[MonitorInfo] = []
    claimed_outputs: set[str] = set()

    for entry in cached:
        bus = entry.get("bus")
        if bus is None:
            continue
        out_name = entry.get("output_name")
        is_internal = entry.get("is_internal", bus < 0)
        c_br = entry.get("brightness", 50)
        c_co = entry.get("contrast", 50)
        c_ct = entry.get("color_temp", COLOR_TEMP_NEUTRAL)

        if is_internal or bus < 0:
            if not include_internal:
                continue
            effective_out = out_name
            if effective_out and effective_out not in connected_outputs:
                internal_outs = [k for k in connected_outputs if re.match(r'^(eDP|LVDS|DSI)', k, re.IGNORECASE)]
                effective_out = internal_outs[0] if internal_outs else None
            if effective_out:
                claimed_outputs.add(effective_out)
            crtc_idx = outs.get(effective_out) if effective_out else None
            dev = entry.get("device") or "/sys/class/backlight/intel_backlight"
            monitors.append(MonitorInfo(
                bus=bus,
                device=dev,
                name=entry.get("name") or f"Laptop ({effective_out or 'internal'})",
                brightness=BacklightController(dev, effective_out),
                contrast=SoftwareContrastController(effective_out),
                output_name=effective_out,
                crtc_index=crtc_idx,
                is_internal=True,
                current_brightness=c_br,
                current_contrast=c_co,
                current_color_temp=c_ct,
            ))
        else:
            dev = f"/dev/i2c-{bus}"
            if not os.path.exists(dev):
                return None  # Hardware bus missing, fallback to full probe
            resolved_out, resolved_crtc = resolve_output_for_bus(bus)
            effective_out = resolved_out or out_name
            if effective_out and effective_out not in connected_outputs:
                # Connected outputs does not contain this cached external display -> it is unplugged!
                continue
            if effective_out:
                claimed_outputs.add(effective_out)
            monitors.append(MonitorInfo(
                bus=bus,
                device=dev,
                name=entry.get("name", "External Display"),
                brightness=DDCController(bus, vcp_brightness),
                contrast=DDCController(bus, vcp_contrast),
                output_name=effective_out,
                crtc_index=resolved_crtc or outs.get(effective_out),
                is_internal=False,
                current_brightness=c_br,
                current_contrast=c_co,
                current_color_temp=c_ct,
            ))

    # If any connected output was NOT in cache, do full hardware probe
    unclaimed = connected_outputs - claimed_outputs
    if unclaimed:
        return None

    return monitors if monitors else None


def build_monitors_from_cache(cached: list[dict], vcp_brightness: int,
                              vcp_contrast: int, include_internal: bool = True) -> list[MonitorInfo]:
    """Compatibility wrapper for build_monitors_from_cache."""
    result = fast_build_from_cache(cached, vcp_brightness, vcp_contrast, include_internal)
    if result is not None:
        return result
    return probe_all_monitors(vcp_brightness, vcp_contrast, include_internal=include_internal, cached_state=cached)


# ---------------------------------------------------------------------------
#  State cache
# ---------------------------------------------------------------------------

def load_state() -> list[dict] | None:
    try:
        with open(DEFAULT_STATE_PATH) as f:
            data = json.load(f)
        age = time.time() - data.get("timestamp", 0)
        if age > STATE_MAX_AGE:
            print(f"[{APP_NAME}] State cache too old ({age:.0f}s), re-probing", file=sys.stderr)
            return None
        monitors = data.get("monitors", [])
        return monitors if monitors else None
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def save_state(monitors: list[MonitorInfo], values: dict[int, dict]):
    data = {
        "timestamp": time.time(),
        "monitors": [
            {
                "bus": m.bus,
                "name": m.name,
                "device": m.device,
                "output_name": m.output_name,
                "is_internal": m.is_internal,
                "brightness": values.get(m.bus, {}).get("brightness", m.current_brightness),
                "contrast": values.get(m.bus, {}).get("contrast", m.current_contrast),
                "color_temp": values.get(m.bus, {}).get("color_temp", m.current_color_temp),
            }
            for m in monitors
        ],
    }
    try:
        os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)
        with open(DEFAULT_STATE_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        print(f"[{APP_NAME}] Error saving state: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
#  DDC controller via ddcutil (with non-blocking latest-target queue)
# ---------------------------------------------------------------------------

class DDCController:
    _bus_locks: dict[int, threading.Lock] = {}
    _locks_lock = threading.Lock()

    def __init__(self, bus: int, feature: int):
        self.bus = bus
        self.feature = feature
        if isinstance(feature, int):
            self._feature_hex = f"0x{feature:02x}"
        elif isinstance(feature, str) and not str(feature).startswith("0x"):
            try:
                self._feature_hex = f"0x{int(feature):02x}"
            except ValueError:
                self._feature_hex = f"0x{feature}"
        else:
            self._feature_hex = str(feature)

        with DDCController._locks_lock:
            if bus not in DDCController._bus_locks:
                DDCController._bus_locks[bus] = threading.Lock()
        self._lock = DDCController._bus_locks[bus]
        self._target_value: int | None = None
        self._target_lock = threading.Lock()
        self._worker_running = False

    def get_value(self) -> int | None:
        with self._lock:
            try:
                result = subprocess.run(
                    ["ddcutil", "getvcp", self._feature_hex,
                     "--bus", str(self.bus), "--terse"],
                    capture_output=True, text=True, timeout=6
                )
                m = re.search(r'VCP\s+\w+\s+\w+\s+(\d+)\s+(\d+)', result.stdout)
                if m:
                    return int(m.group(1))
                m = re.search(r'current value\s*=\s*(\d+)', result.stdout)
                if m:
                    return int(m.group(1))
                return None
            except Exception:
                return None

    def set_value(self, value: int) -> bool:
        value = max(0, min(100, int(value)))
        with self._target_lock:
            self._target_value = value
            if self._worker_running:
                return True
            self._worker_running = True

        def _worker():
            while True:
                with self._target_lock:
                    val = self._target_value
                    if val is None:
                        self._worker_running = False
                        break
                    self._target_value = None
                with self._lock:
                    try:
                        cmd = ["ddcutil", "setvcp", self._feature_hex, str(val),
                               "--bus", str(self.bus), "--noverify"]
                        subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()
        return True


# ---------------------------------------------------------------------------
#  Slider group widget
# ---------------------------------------------------------------------------

class _SliderGroup:
    def __init__(self, vbox, monitor: MonitorInfo | None, min_val, max_val, step,
                 on_brightness, on_contrast, show_presets=False,
                 on_color_temp=None, show_contrast=True, show_color_temp=True,
                 color_temp_min=COLOR_TEMP_MIN, color_temp_max=COLOR_TEMP_MAX):
        self.monitor = monitor
        self.is_applying_brightness = False
        self.is_applying_contrast = False
        self.is_applying_color_temp = False
        self._brightness_debounce = None
        self._contrast_debounce = None
        self._color_temp_debounce = None
        self._on_brightness = on_brightness
        self._on_contrast = on_contrast
        self._on_color_temp = on_color_temp
        self.contrast_scale = None
        self.color_temp_scale = None
        self.color_temp_label = None

        # --- Brightness ---
        title = Gtk.Label()
        title.set_markup(f"<b>{_('brightness')}</b>")
        title.set_xalign(0.0)
        vbox.pack_start(title, False, False, 0)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vbox.pack_start(hbox, True, True, 0)

        adj = Gtk.Adjustment(value=50, lower=min_val, upper=max_val,
                             step_increment=step, page_increment=step * 2, page_size=0)
        self.brightness_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        self.brightness_scale.set_digits(0)
        self.brightness_scale.set_draw_value(False)
        self.brightness_scale.set_size_request(220, -1)
        for tick in range(min_val, max_val + 1, 25):
            self.brightness_scale.add_mark(tick, Gtk.PositionType.BOTTOM, None)
        self.brightness_scale.connect("value-changed", self._on_brightness_changed)
        hbox.pack_start(self.brightness_scale, True, True, 0)

        self.brightness_label = Gtk.Label(label="50%")
        self.brightness_label.set_width_chars(5)
        hbox.pack_start(self.brightness_label, False, False, 0)

        if show_presets:
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            btn_box.set_homogeneous(True)
            vbox.pack_start(btn_box, False, False, 0)
            for preset in [5, 25, 50, 75, 100]:
                btn = Gtk.Button(label=f"{preset}%")
                btn.connect("clicked", self._on_preset_clicked, preset)
                btn_box.pack_start(btn, True, True, 0)

        # --- Contrast (optional) ---
        if show_contrast:
            contrast_title = Gtk.Label()
            contrast_title.set_markup(f"<b>{_('contrast')}</b>")
            contrast_title.set_xalign(0.0)
            vbox.pack_start(contrast_title, False, False, 0)

            contrast_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            vbox.pack_start(contrast_hbox, True, True, 0)

            contrast_adj = Gtk.Adjustment(value=50, lower=min_val, upper=max_val,
                                          step_increment=step, page_increment=step * 2, page_size=0)
            self.contrast_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=contrast_adj)
            self.contrast_scale.set_digits(0)
            self.contrast_scale.set_draw_value(False)
            self.contrast_scale.set_size_request(220, -1)
            for tick in range(min_val, max_val + 1, 25):
                self.contrast_scale.add_mark(tick, Gtk.PositionType.BOTTOM, None)
            self.contrast_scale.connect("value-changed", self._on_contrast_changed)
            contrast_hbox.pack_start(self.contrast_scale, True, True, 0)

            self.contrast_label = Gtk.Label(label="50%")
            self.contrast_label.set_width_chars(5)
            contrast_hbox.pack_start(self.contrast_label, False, False, 0)

        # --- Color temperature (optional) ---
        if show_color_temp and on_color_temp is not None:
            ct_title = Gtk.Label()
            ct_title.set_markup(f"<b>{_('color_temp')}</b>")
            ct_title.set_xalign(0.0)
            vbox.pack_start(ct_title, False, False, 0)

            ct_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            vbox.pack_start(ct_hbox, True, True, 0)

            ct_adj = Gtk.Adjustment(value=COLOR_TEMP_NEUTRAL,
                                    lower=color_temp_min, upper=color_temp_max,
                                    step_increment=COLOR_TEMP_STEP,
                                    page_increment=COLOR_TEMP_STEP * 5,
                                    page_size=0)
            self.color_temp_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                              adjustment=ct_adj)
            self.color_temp_scale.set_digits(0)
            self.color_temp_scale.set_draw_value(False)
            self.color_temp_scale.set_size_request(220, -1)
            for tick in COLOR_TEMP_MARKS:
                if color_temp_min <= tick <= color_temp_max:
                    self.color_temp_scale.add_mark(tick, Gtk.PositionType.BOTTOM, None)
            self.color_temp_scale.connect("value-changed", self._on_color_temp_changed)
            ct_hbox.pack_start(self.color_temp_scale, True, True, 0)

            self.color_temp_label = Gtk.Label(label=f"{COLOR_TEMP_NEUTRAL}K")
            self.color_temp_label.set_width_chars(6)
            ct_hbox.pack_start(self.color_temp_label, False, False, 0)

            if show_presets:
                ct_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                ct_btn_box.set_homogeneous(True)
                vbox.pack_start(ct_btn_box, False, False, 0)
                for temp in [2700, 3500, 4500, 5500, 6500]:
                    if color_temp_min <= temp <= color_temp_max:
                        btn = Gtk.Button(label=f"{temp}K")
                        btn.connect("clicked", self._on_color_temp_preset_clicked, temp)
                        ct_btn_box.pack_start(btn, True, True, 0)

    def refresh(self):
        if self.monitor is None:
            return
        b = self.monitor.brightness.get_value()
        c = self.monitor.contrast.get_value() if self.contrast_scale else None
        if b is not None:
            GLib.idle_add(self.set_brightness, b)
        if c is not None and self.contrast_scale:
            GLib.idle_add(self.set_contrast, c)

    def set_brightness(self, value):
        self.is_applying_brightness = True
        self.brightness_scale.set_value(value)
        self.brightness_label.set_text(f"{int(value)}%")
        self.is_applying_brightness = False

    def set_contrast(self, value):
        if not self.contrast_scale:
            return
        self.is_applying_contrast = True
        self.contrast_scale.set_value(value)
        self.contrast_label.set_text(f"{int(value)}%")
        self.is_applying_contrast = False

    def _on_brightness_changed(self, scale):
        val = int(scale.get_value())
        self.brightness_label.set_text(f"{val}%")
        if self.is_applying_brightness:
            return
        if self._brightness_debounce:
            GLib.source_remove(self._brightness_debounce)
        self._brightness_debounce = GLib.timeout_add(150, self._apply_brightness, val)

    def _apply_brightness(self, value):
        self._brightness_debounce = None
        self._on_brightness(self, value)
        return False

    def _on_contrast_changed(self, scale):
        if not self.contrast_scale:
            return
        val = int(scale.get_value())
        self.contrast_label.set_text(f"{val}%")
        if self.is_applying_contrast:
            return
        if self._contrast_debounce:
            GLib.source_remove(self._contrast_debounce)
        self._contrast_debounce = GLib.timeout_add(150, self._apply_contrast, val)

    def _apply_contrast(self, value):
        self._contrast_debounce = None
        self._on_contrast(self, value)
        return False

    def _on_preset_clicked(self, button, value):
        self.set_brightness(value)
        self._apply_brightness(value)

    def set_color_temp(self, value):
        if self.color_temp_scale is None:
            return
        self.is_applying_color_temp = True
        self.color_temp_scale.set_value(value)
        self.color_temp_label.set_text(f"{int(value)}K")
        self.is_applying_color_temp = False

    def _on_color_temp_changed(self, scale):
        val = int(scale.get_value())
        if self.color_temp_label:
            self.color_temp_label.set_text(f"{val}K")
        if self.is_applying_color_temp or self._on_color_temp is None:
            return
        if self._color_temp_debounce:
            GLib.source_remove(self._color_temp_debounce)
        self._color_temp_debounce = GLib.timeout_add(150, self._apply_color_temp, val)

    def _apply_color_temp(self, value):
        self._color_temp_debounce = None
        if self._on_color_temp:
            self._on_color_temp(self, value)
        return False

    def _on_color_temp_preset_clicked(self, button, value):
        self.set_color_temp(value)
        self._apply_color_temp(value)


# ---------------------------------------------------------------------------
#  Brightness popup window
# ---------------------------------------------------------------------------

class BrightnessPopup(Gtk.Window):

    def __init__(self, monitors: list[MonitorInfo], min_val: int, max_val: int, step: int,
                 on_color_temp=None, on_contrast=None, on_value_changed=None, config: dict | None = None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        self.monitors = monitors
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.config = config or DEFAULT_CONFIG
        self._on_color_temp = on_color_temp
        self._on_contrast = on_contrast
        self._on_value_changed = on_value_changed
        self._visible = False
        self._position = (0, 0)
        self._last_toggle_coords = (100, 100)
        self._monitor_groups: list[_SliderGroup] = []
        self._master_group: _SliderGroup | None = None
        self._ignore_focus_loss_until = 0.0
        self._had_focus = False

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        self.set_keep_above(True)
        self.set_border_width(10)
        self.set_accept_focus(True)
        self.set_can_focus(True)
        self.set_gravity(Gdk.Gravity.NORTH_WEST)
        self.set_position(Gtk.WindowPosition.NONE)

        self.connect("focus-in-event", self._on_focus_in)
        self.connect("focus-out-event", self._on_focus_out)
        self.connect("key-press-event", self._on_key_press)
        self.connect("show", lambda w: self._set_visible(True))
        self.connect("hide", lambda w: self._set_visible(False))
        self.connect("realize", self._on_realize)

        self._main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(self._main_box)

        self._populate_ui()

        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window {
                background-color: @theme_bg_color;
                border: 1px solid @borders;
                border-radius: 8px;
            }
            frame {
                border-radius: 6px;
                background-color: alpha(@theme_base_color, 0.4);
            }
            button {
                min-height: 22px;
                padding: 2px 4px;
                font-size: 11px;
                border-radius: 4px;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _populate_ui(self):
        multi = len(self.monitors) > 1
        show_contrast = self.config.get("show_contrast_slider", True)
        show_ct = self.config.get("show_color_temp_slider", True)
        ct_min = self.config.get("color_temp_min", COLOR_TEMP_MIN)
        ct_max = self.config.get("color_temp_max", COLOR_TEMP_MAX)
        custom_names = self.config.get("custom_display_names", {})

        ct_master_cb = self._on_master_color_temp if self._on_color_temp and show_ct else None
        ct_per_mon_cb = self._on_monitor_color_temp if self._on_color_temp and show_ct else None

        if multi:
            master_frame = Gtk.Frame()
            master_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
            master_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            master_box.set_border_width(8)
            master_frame.add(master_box)
            self._main_box.pack_start(master_frame, False, False, 0)

            header = Gtk.Label()
            header.set_markup(f"<b>{_('all_monitors')}</b>")
            header.set_xalign(0.0)
            master_box.pack_start(header, False, False, 0)

            self._master_group = _SliderGroup(
                master_box, None, self.min_val, self.max_val, self.step,
                on_brightness=self._on_master_brightness,
                on_contrast=self._on_master_contrast,
                show_presets=True,
                on_color_temp=ct_master_cb,
                show_contrast=show_contrast,
                show_color_temp=show_ct,
                color_temp_min=ct_min,
                color_temp_max=ct_max)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(160)
        scroll.set_max_content_height(480)
        scroll.set_propagate_natural_height(True)
        self._main_box.pack_start(scroll, True, True, 0)

        monitors_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroll.add(monitors_box)

        for mon in self.monitors:
            mon_frame = Gtk.Frame()
            mon_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
            mon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            mon_box.set_border_width(8)
            mon_frame.add(mon_box)
            monitors_box.pack_start(mon_frame, False, False, 0)

            if mon.is_internal:
                icon_tag = "💻"
                default_name = f"Laptop ({mon.output_name or 'Built-in'})"
            else:
                icon_tag = "🖥"
                default_name = mon.name or mon.device
                if mon.output_name and mon.output_name not in default_name:
                    default_name = f"{default_name} — {mon.output_name}"

            custom_title = custom_names.get(str(mon.bus)) or custom_names.get(mon.output_name or "")
            title_text = f"{icon_tag} {custom_title or default_name}"

            header = Gtk.Label()
            header.set_markup(f"<b>{GLib.markup_escape_text(title_text)}</b>")
            header.set_xalign(0.0)
            mon_box.pack_start(header, False, False, 0)

            group = _SliderGroup(
                mon_box, mon, self.min_val, self.max_val, self.step,
                on_brightness=self._on_monitor_brightness,
                on_contrast=self._on_monitor_contrast,
                show_presets=not multi,
                on_color_temp=ct_per_mon_cb,
                show_contrast=show_contrast,
                show_color_temp=show_ct,
                color_temp_min=ct_min,
                color_temp_max=ct_max)

            group.set_brightness(mon.current_brightness)
            if group.contrast_scale:
                group.set_contrast(mon.current_contrast)
            if group.color_temp_scale:
                group.set_color_temp(mon.current_color_temp)

            self._monitor_groups.append(group)

        self._sync_master()

    def rebuild_monitors(self, new_monitors: list[MonitorInfo]):
        self.monitors = new_monitors
        for child in self._main_box.get_children():
            self._main_box.remove(child)
        self._monitor_groups.clear()
        self._master_group = None
        self._populate_ui()
        self.show_all()

    def _notify_changed(self):
        if self._on_value_changed:
            self._on_value_changed()

    def _on_monitor_color_temp(self, group: _SliderGroup, value: int):
        if group.monitor is not None:
            group.monitor.current_color_temp = value
            if self._on_color_temp:
                self._on_color_temp(group.monitor, value)
        self._sync_master()
        self._notify_changed()

    def _on_master_color_temp(self, group: _SliderGroup, value: int):
        for mg in self._monitor_groups:
            mg.set_color_temp(value)
            if mg.monitor is not None:
                mg.monitor.current_color_temp = value
        def _do():
            for mg in self._monitor_groups:
                if mg.monitor is not None and self._on_color_temp:
                    self._on_color_temp(mg.monitor, value)
        threading.Thread(target=_do, daemon=True).start()
        self._notify_changed()

    def _on_monitor_brightness(self, group: _SliderGroup, value: int):
        if group.monitor is not None:
            group.monitor.current_brightness = value
            threading.Thread(target=group.monitor.brightness.set_value, args=(value,), daemon=True).start()
        self._sync_master()
        self._notify_changed()

    def _on_monitor_contrast(self, group: _SliderGroup, value: int):
        if group.monitor is not None:
            group.monitor.current_contrast = value
            if self._on_contrast:
                self._on_contrast(group.monitor, value)
        self._sync_master()
        self._notify_changed()

    def _on_master_brightness(self, group: _SliderGroup, value: int):
        for mg in self._monitor_groups:
            mg.set_brightness(value)
            if mg.monitor is not None:
                mg.monitor.current_brightness = value
        def _do():
            for mg in self._monitor_groups:
                if mg.monitor is not None:
                    mg.monitor.brightness.set_value(value)
        threading.Thread(target=_do, daemon=True).start()
        self._notify_changed()

    def _on_master_contrast(self, group: _SliderGroup, value: int):
        for mg in self._monitor_groups:
            mg.set_contrast(value)
            if mg.monitor is not None:
                mg.monitor.current_contrast = value
        def _do():
            for mg in self._monitor_groups:
                if mg.monitor is not None and self._on_contrast:
                    self._on_contrast(mg.monitor, value)
        threading.Thread(target=_do, daemon=True).start()
        self._notify_changed()

    def _on_realize(self, widget):
        self.get_window().move_resize(
            self._position[0], self._position[1],
            self.get_allocated_width(), self.get_allocated_height()
        )

    def refresh_value(self):
        def _do_refresh():
            results = {}
            for group in self._monitor_groups:
                mon = group.monitor
                b = mon.brightness.get_value()
                c = mon.contrast.get_value() if group.contrast_scale else None
                results[mon.bus] = (b, c)
            GLib.idle_add(self._apply_hw_results, results)

        threading.Thread(target=_do_refresh, daemon=True).start()

    def _apply_hw_results(self, results: dict):
        for group in self._monitor_groups:
            vals = results.get(group.monitor.bus)
            if vals:
                b, c = vals
                if b is not None:
                    group.set_brightness(b)
                    group.monitor.current_brightness = b
                if c is not None and group.contrast_scale:
                    group.set_contrast(c)
                    group.monitor.current_contrast = c
        self._sync_master()
        self._notify_changed()
        return False

    def _sync_master(self):
        if self._master_group and self._monitor_groups:
            avg_b = sum(int(mg.brightness_scale.get_value()) for mg in self._monitor_groups) // len(self._monitor_groups)
            self._master_group.set_brightness(avg_b)
            if self._master_group.contrast_scale:
                c_groups = [mg for mg in self._monitor_groups if mg.contrast_scale]
                if c_groups:
                    avg_c = sum(int(mg.contrast_scale.get_value()) for mg in c_groups) // len(c_groups)
                    self._master_group.set_contrast(avg_c)
            if self._master_group.color_temp_scale:
                ct_groups = [mg for mg in self._monitor_groups if mg.color_temp_scale]
                if ct_groups:
                    avg_ct = sum(int(mg.color_temp_scale.get_value()) for mg in ct_groups) // len(ct_groups)
                    self._master_group.set_color_temp(avg_ct)

    def apply_cached_values(self, cached: list[dict]):
        cache_map = {entry["bus"]: entry for entry in cached}
        for group in self._monitor_groups:
            entry = cache_map.get(group.monitor.bus)
            if entry:
                b = entry.get("brightness", 50)
                c = entry.get("contrast", 50)
                t = entry.get("color_temp", COLOR_TEMP_NEUTRAL)
                group.set_brightness(b)
                if group.monitor is not None:
                    group.monitor.current_brightness = b
                    group.monitor.current_contrast = c
                    group.monitor.current_color_temp = t
                if group.contrast_scale:
                    group.set_contrast(c)
                if group.color_temp_scale:
                    group.set_color_temp(t)
        self._sync_master()

    def update_all(self, brightness: int, contrast: int | None = None, color_temp: int | None = None):
        for group in self._monitor_groups:
            group.set_brightness(brightness)
            if group.monitor is not None:
                group.monitor.current_brightness = brightness
                if contrast is not None:
                    group.monitor.current_contrast = contrast
                if color_temp is not None:
                    group.monitor.current_color_temp = color_temp
            if contrast is not None and group.contrast_scale:
                group.set_contrast(contrast)
            if color_temp is not None and group.color_temp_scale:
                group.set_color_temp(color_temp)
        if self._master_group:
            self._master_group.set_brightness(brightness)
            if contrast is not None and self._master_group.contrast_scale:
                self._master_group.set_contrast(contrast)
            if color_temp is not None and self._master_group.color_temp_scale:
                self._master_group.set_color_temp(color_temp)

    def update_value(self, value):
        for group in self._monitor_groups:
            group.set_brightness(value)
            if group.monitor is not None:
                group.monitor.current_brightness = value
        if self._master_group:
            self._master_group.set_brightness(value)

    def hide(self):
        super().hide()

    def _set_visible(self, visible):
        self._visible = visible
        if not visible:
            self._had_focus = False

    def _on_focus_in(self, widget, event):
        self._had_focus = True
        return False

    def _on_focus_out(self, widget, event):
        if self._had_focus:
            GLib.timeout_add(150, self._check_focus)
        return False

    def _check_focus(self):
        if time.time() < self._ignore_focus_loss_until:
            return False
        if self._visible and self._had_focus and not self.has_toplevel_focus():
            self.hide()
        return False

    def _on_key_press(self, widget, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_q):
            self.hide()
            return True
        return False

    def toggle_at(self, x: int, y: int):
        print(f"[{APP_NAME}] BrightnessPopup.toggle_at({x}, {y}) called! visible={self._visible}", file=sys.stderr)
        self._last_toggle_coords = (x, y)
        if self._visible:
            self.hide()
        else:
            self._had_focus = False
            self.refresh_value()
            self._ignore_focus_loss_until = time.time() + 1.0
            self.show_all()
            display = Gdk.Display.get_default()
            monitor = display.get_monitor_at_point(x, y) if display else None

            pref_size = self.get_preferred_size()[1]
            popup_width = max(310, pref_size.width)
            popup_height = max(560, pref_size.height)

            if monitor:
                wa = monitor.get_workarea()
                px = max(wa.x + 10, min(x - popup_width // 2, wa.x + wa.width - popup_width - 10))
                if y + popup_height + 10 <= wa.y + wa.height:
                    py = y + 10
                elif y - popup_height - 10 >= wa.y:
                    py = y - popup_height - 10
                else:
                    py = max(wa.y + 10, wa.y + wa.height - popup_height - 10)
            else:
                px, py = x, y

            self._position = (px, py)
            self.move(px, py)
            self.present()
            if self.get_window():
                self.get_window().focus(Gdk.CURRENT_TIME)


# ---------------------------------------------------------------------------
#  Configuration loader
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    try:
        with open(path) as f:
            cfg = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(cfg)
        return merged
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[{APP_NAME}] Warning: cannot load config from {path}: {e}", file=sys.stderr)
        return DEFAULT_CONFIG.copy()


# ---------------------------------------------------------------------------
#  Display Hotplug Watcher
# ---------------------------------------------------------------------------

class DisplayHotplugWatcher:
    """Watches for display hotplug events via GDK signals and DRM sysfs polling."""

    def __init__(self, callback):
        self.callback = callback
        self._last_drm_state = self._read_drm_state()
        self._debounce_id = None

        screen = Gdk.Screen.get_default()
        if screen:
            screen.connect("monitors-changed", self._on_change)
        display = Gdk.Display.get_default()
        if display:
            display.connect("monitor-added", self._on_change)
            display.connect("monitor-removed", self._on_change)

        GLib.timeout_add_seconds(2, self._poll_drm)

    def _read_drm_state(self) -> dict[str, str]:
        state = {}
        for p in glob.glob("/sys/class/drm/card*-*/status"):
            try:
                with open(p, "r") as f:
                    state[p] = f.read().strip()
            except OSError:
                pass
        return state

    def _poll_drm(self) -> bool:
        new_state = self._read_drm_state()
        if new_state != self._last_drm_state:
            self._last_drm_state = new_state
            self._on_change()
        return True

    def _on_change(self, *args):
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
        self._debounce_id = GLib.timeout_add(600, self._fire)

    def _fire(self) -> bool:
        self._debounce_id = None
        self.callback()
        return False


# ---------------------------------------------------------------------------
#  Automatic Day/Night Mode Scheduler
# ---------------------------------------------------------------------------

def parse_time_to_minutes(time_str: str) -> int:
    """Parse 'HH:MM' string to minutes since midnight."""
    try:
        parts = time_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 7 * 60


def get_current_period(day_time_str: str, night_time_str: str, now: datetime.datetime | None = None) -> str:
    """Returns 'day' or 'night' based on whether current time falls within the daytime window."""
    if now is None:
        now = datetime.datetime.now()
    now_m = now.hour * 60 + now.minute
    d_m = parse_time_to_minutes(day_time_str)
    n_m = parse_time_to_minutes(night_time_str)

    if d_m < n_m:
        return "day" if (d_m <= now_m < n_m) else "night"
    else:
        return "day" if (now_m >= d_m or now_m < n_m) else "night"


class DayNightScheduler:
    """Manages automatic day/night mode transitions based on clock time events."""

    def __init__(self, app: 'TrayApp'):
        self.app = app
        self._enabled = bool(self.app.config.get("auto_schedule_enabled", True))
        self._current_period = None
        self._timer_id = None
        self._last_tick_time = time.time()

    def start(self):
        if self._timer_id is None:
            self._check(initial=True)
            self._timer_id = GLib.timeout_add_seconds(15, self._tick)

    def stop(self):
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.app.config["auto_schedule_enabled"] = enabled
        save_config_file(self.app.config)
        self.app.update_tooltip()
        if enabled:
            self._check(initial=True)

    def get_period(self, now: datetime.datetime | None = None) -> str:
        d_t = self.app.config.get("day_time", "07:00")
        n_t = self.app.config.get("night_time", "19:00")
        return get_current_period(d_t, n_t, now)

    def _tick(self) -> bool:
        now_ts = time.time()
        # If jump > 45 seconds, system resumed from suspend/sleep
        resumed = (now_ts - self._last_tick_time) > 45
        self._last_tick_time = now_ts
        self._check(initial=resumed)
        return True

    def _check(self, initial: bool = False):
        if not self._enabled:
            return

        period = self.get_period()
        if initial:
            # On startup or wake from suspend
            if self._current_period != period:
                self._current_period = period
                print(f"[{APP_NAME}] Auto schedule initialized: currently {period.upper()} mode.", file=sys.stderr)
                self.apply_period(period, notify=False, smooth=False)
            else:
                self.app.update_tooltip()
        else:
            # Scheduled time event crossing
            if self._current_period != period:
                old_period = self._current_period
                self._current_period = period
                print(f"[{APP_NAME}] ⏰ Auto Day/Night Time Event: Switched from {old_period} to {period.upper()} mode!", file=sys.stderr)
                self.apply_period(period, notify=True, smooth=True)

    def apply_period(self, period: str, notify: bool = True, smooth: bool = True):
        if period == "day":
            br = int(self.app.config.get("day_mode_brightness", 100))
            co = int(self.app.config.get("day_mode_contrast", 75))
            ct = int(self.app.config.get("day_mode_temp", 6500))
            label = "Day Mode ☀"
            icon_name = "display-brightness"
        else:
            br = int(self.app.config.get("night_mode_brightness", 35))
            co = int(self.app.config.get("night_mode_contrast", 50))
            ct = int(self.app.config.get("night_mode_temp", 2700))
            label = "Night Mode 🌙"
            icon_name = "weather-clear-night"

        self.app._night_mode_active = (period == "night")

        if smooth and self.app.config.get("smooth_transition", True):
            self.app.smooth_transition_to(br, co, ct)
        else:
            self.app.apply_preset_values_instant(br, co, ct)

        if notify and self.app.config.get("schedule_notifications", True):
            send_desktop_notification(f"DDC Slider: {label}", f"Automatic time event: set {br}% brightness, {ct}K warmth.", icon=icon_name)

        self.app.update_tooltip()


# ---------------------------------------------------------------------------
#  Tray Application
# ---------------------------------------------------------------------------

class TrayApp:

    def __init__(self, monitors: list[MonitorInfo], min_val: int, max_val: int, step: int,
                 scroll_step: int = DEFAULT_SCROLL_STEP, config: dict | None = None,
                 cached_state: list[dict] | None = None, icon_style: str | None = None,
                 original_cmd: str | None = None):
        self.monitors = monitors
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.scroll_step = scroll_step
        self.config = config or DEFAULT_CONFIG
        self.presets = self.config.get("presets", [])
        self.original_cmd = original_cmd or sys.argv[0]
        self._night_mode_active = False
        self._saved_daylight_state = None
        self._transition_thread = None
        self._transition_cancel = threading.Event()

        self.popup = BrightnessPopup(monitors, min_val, max_val, step,
                                     on_color_temp=self._on_color_temp,
                                     on_contrast=self._on_contrast,
                                     on_value_changed=self._save_current_state,
                                     config=self.config)
        self._cached_brightness = None
        self._scroll_debounce_id = None
        self._redshift_paused = False
        self._icon_path = _get_icon_path(icon_style)

        if cached_state:
            self.popup.apply_cached_values(cached_state)
            self._restore_color_temps(cached_state)

        self.status_icon = None
        self.indicator = None

        n = len(monitors)
        tooltip = _("tooltip_multi", n=n) if n > 1 else _("tooltip")

        # Prioritize Gtk.StatusIcon for native left-click direct popup on desktop panels (XFCE, MATE, etc.)
        tray_ready = False
        if self._setup_status_icon(tooltip):
            tray_ready = True
            print(f"[{APP_NAME}] Tray icon initialized using Gtk.StatusIcon (native direct left-click)", file=sys.stderr)
        else:
            for libname in ('AyatanaAppIndicator3', 'AppIndicator3'):
                try:
                    gi.require_version(libname, '0.1')
                    mod = __import__('gi.repository.' + libname, fromlist=[libname])
                    self._setup_appindicator(mod, tooltip)
                    tray_ready = True
                    print(f"[{APP_NAME}] Tray icon initialized using {libname}", file=sys.stderr)
                    break
                except Exception:
                    pass

        if not tray_ready:
            print(f"[{APP_NAME}] ERROR: No tray icon backend available!", file=sys.stderr)
            sys.exit(1)

        # Monitor hotplug watcher
        self.hotplug_watcher = DisplayHotplugWatcher(self._on_hotplug_detected)

        # Start single-instance IPC socket server
        self._setup_ipc_server()

        # Automatic Day/Night Mode Scheduler
        self.scheduler = DayNightScheduler(self)
        self.scheduler.start()

    def update_tooltip(self):
        n = len(self.monitors)
        base = _("tooltip_multi", n=n) if n > 1 else _("tooltip")
        if hasattr(self, "scheduler") and self.scheduler.is_enabled():
            p = self.scheduler.get_period()
            tag = "  [Auto: 🌙 Night]" if p == "night" else "  [Auto: ☀ Day]"
            tooltip = base + tag
        else:
            tooltip = base
        if self.status_icon:
            self.status_icon.set_tooltip_text(tooltip)
        elif self.indicator:
            self.indicator.set_title(tooltip)

    def smooth_transition_to(self, target_br: int, target_co: int, target_ct: int):
        """Cross-fade all displays smoothly to the target brightness, contrast, and color temperature."""
        if self._transition_thread and self._transition_thread.is_alive():
            self._transition_cancel.set()
            self._transition_thread.join(timeout=0.4)

        self._transition_cancel.clear()

        start_states = []
        for m in self.monitors:
            b0 = m.current_brightness if m.current_brightness is not None else 50
            c0 = m.current_contrast if m.current_contrast is not None else 50
            t0 = m.current_color_temp if m.current_color_temp is not None else COLOR_TEMP_NEUTRAL
            start_states.append((m, b0, c0, t0))

        duration = float(self.config.get("transition_duration_sec", 3.0))
        steps = max(5, int(duration / 0.2))
        interval = duration / steps

        def _worker():
            for step in range(1, steps + 1):
                if self._transition_cancel.is_set():
                    return
                progress = step / steps
                ease = 0.5 * (1.0 - math.cos(math.pi * progress))

                for m, b0, c0, t0 in start_states:
                    cb = int(round(b0 + ease * (target_br - b0)))
                    cc = int(round(c0 + ease * (target_co - c0)))
                    ct = int(round((t0 + ease * (target_ct - t0)) / 50.0)) * 50

                    m.current_brightness = cb
                    m.current_contrast = cc
                    m.current_color_temp = ct
                    m.brightness.set_value(cb)
                    TrayApp.apply_display_color_contrast(m, contrast=cc, color_temp=ct)

                curr_br = int(round(start_states[0][1] + ease * (target_br - start_states[0][1])))
                curr_co = int(round(start_states[0][2] + ease * (target_co - start_states[0][2])))
                curr_ct = int(round((start_states[0][3] + ease * (target_ct - start_states[0][3])) / 50.0)) * 50
                GLib.idle_add(self.popup.update_all, curr_br, curr_co, curr_ct)

                if self._transition_cancel.wait(interval):
                    return

            self._save_current_state()

        self._transition_thread = threading.Thread(target=_worker, daemon=True)
        self._transition_thread.start()

    def apply_preset_values_instant(self, br: int, co: int, ct: int):
        """Immediately apply brightness, contrast, and color temperature to all displays."""
        self.popup.update_all(brightness=br, contrast=co, color_temp=ct)
        def _do():
            for m in self.monitors:
                m.current_brightness = br
                m.current_contrast = co
                m.current_color_temp = ct
                m.brightness.set_value(br)
                TrayApp.apply_display_color_contrast(m, contrast=co, color_temp=ct)
            self._save_current_state()
        threading.Thread(target=_do, daemon=True).start()

    def _switch_to_day(self):
        self.scheduler.apply_period("day", notify=True, smooth=True)

    def _switch_to_night(self):
        self.scheduler.apply_period("night", notify=True, smooth=True)

    def _toggle_auto_schedule(self):
        new_val = not self.scheduler.is_enabled()
        self.scheduler.set_enabled(new_val)

    def _on_toggle_auto_schedule(self, widget):
        enabled = widget.get_active()
        self.scheduler.set_enabled(enabled)
        status_msg = "Enabled" if enabled else "Disabled"
        print(f"[{APP_NAME}] Auto Day/Night schedule {status_msg.lower()}.", file=sys.stderr)
        d_t = self.config.get("day_time", "07:00")
        n_t = self.config.get("night_time", "19:00")
        msg = f"Schedule: Day at {d_t}, Night at {n_t}" if enabled else "Manual mode active"
        send_desktop_notification(f"Auto Schedule: {status_msg}", msg)

    def _setup_ipc_server(self):
        sock_path = get_socket_path()
        try:
            if os.path.exists(sock_path):
                test_s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_s.settimeout(0.5)
                try:
                    test_s.connect(sock_path)
                    test_s.close()
                    print(f"[{APP_NAME}] Another instance is already active on {sock_path}.", file=sys.stderr)
                    return
                except (ConnectionRefusedError, OSError):
                    try:
                        os.remove(sock_path)
                    except OSError:
                        pass
                finally:
                    test_s.close()

            self._ipc_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._ipc_server.bind(sock_path)
            self._ipc_server.listen(5)
            def _listener():
                while True:
                    try:
                        conn, _ = self._ipc_server.accept()
                        data = conn.recv(1024).strip()
                        conn.close()
                        if data in (b"toggle", b"show"):
                            GLib.idle_add(self._on_remote_toggle)
                        elif data == b"day":
                            GLib.idle_add(self._switch_to_day)
                        elif data == b"night":
                            GLib.idle_add(self._switch_to_night)
                        elif data == b"toggle_night":
                            GLib.idle_add(lambda: self._on_toggle_night_mode(None))
                        elif data == b"auto_toggle":
                            GLib.idle_add(self._toggle_auto_schedule)
                        elif data == b"auto_on":
                            GLib.idle_add(lambda: self.scheduler.set_enabled(True))
                        elif data == b"auto_off":
                            GLib.idle_add(lambda: self.scheduler.set_enabled(False))
                    except Exception:
                        break
            threading.Thread(target=_listener, daemon=True).start()
        except Exception as e:
            print(f"[{APP_NAME}] Warning: cannot start IPC socket: {e}", file=sys.stderr)

    def _on_remote_toggle(self):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat() if display else None
        if seat:
            pointer = seat.get_pointer()
            _, x, y = pointer.get_position()
            self.popup.toggle_at(x, y)
        else:
            self.popup.toggle_at(100, 100)

    def _on_hotplug_detected(self):
        """Handle hardware monitor plug/unplug asynchronously without freezing UI."""
        print(f"[{APP_NAME}] Display change detected! Probing hardware in background...", file=sys.stderr)
        def _bg():
            new_monitors = probe_all_monitors(
                vcp_brightness=VCP_BRIGHTNESS,
                vcp_contrast=VCP_CONTRAST,
                include_internal=self.config.get("include_internal_display", True),
                cached_state=load_state()
            )
            curr_keys = [(m.bus, m.output_name) for m in self.monitors]
            new_keys = [(m.bus, m.output_name) for m in new_monitors]
            if curr_keys != new_keys:
                print(f"[{APP_NAME}] Display configuration changed: {curr_keys} -> {new_keys}", file=sys.stderr)
                GLib.idle_add(self._apply_monitors_update, new_monitors)
        threading.Thread(target=_bg, daemon=True).start()

    def _apply_monitors_update(self, new_monitors: list[MonitorInfo]):
        """Apply newly probed monitors to popup, tooltip, and menus in main thread."""
        self.monitors = new_monitors
        n = len(new_monitors)
        tooltip = _("tooltip_multi", n=n) if n > 1 else _("tooltip")
        if self.status_icon:
            self.status_icon.set_tooltip_text(tooltip)
        if self.indicator:
            self.indicator.set_menu(self._build_menu())
        self.popup.rebuild_monitors(new_monitors)
        self._save_current_state()

        def _apply_all():
            for m in self.monitors:
                TrayApp.apply_display_color_contrast(m, contrast=m.current_contrast, color_temp=m.current_color_temp)
        threading.Thread(target=_apply_all, daemon=True).start()
        return False

    def _save_current_state(self):
        values = {}
        for group in self.popup._monitor_groups:
            mon = group.monitor
            if mon is None:
                continue
            entry = {
                "brightness": int(group.brightness_scale.get_value()),
                "contrast": int(group.contrast_scale.get_value()) if group.contrast_scale else 50,
            }
            if group.color_temp_scale is not None:
                entry["color_temp"] = int(group.color_temp_scale.get_value())
            values[mon.bus] = entry
        save_state(self.monitors, values)

    def _restore_color_temps(self, cached_state: list[dict]):
        cache_map = {entry["bus"]: entry for entry in cached_state}
        def _do():
            for mon in self.monitors:
                entry = cache_map.get(mon.bus)
                if not entry:
                    continue
                co = entry.get("contrast", 50)
                ct = entry.get("color_temp", COLOR_TEMP_NEUTRAL)
                TrayApp.apply_display_color_contrast(mon, contrast=co, color_temp=ct)
        threading.Thread(target=_do, daemon=True).start()

    def _setup_status_icon(self, tooltip: str) -> bool:
        try:
            self.status_icon = Gtk.StatusIcon()
            theme = Gtk.IconTheme.get_default()
            if os.path.exists(self._icon_path):
                self.status_icon.set_from_file(self._icon_path)
            elif theme.has_icon("display-brightness-symbolic"):
                self.status_icon.set_from_icon_name("display-brightness-symbolic")
            else:
                self.status_icon.set_from_icon_name("display-brightness")
            self.status_icon.set_tooltip_text(tooltip)
            self.status_icon.set_visible(True)
            self.status_icon.connect("activate", self._on_left_click)
            self.status_icon.connect("popup-menu", self._on_right_click)
            self.status_icon.connect("scroll-event", self._on_scroll_event)

            def _check_embedded():
                if self.status_icon and not self.status_icon.is_embedded():
                    print(f"[{APP_NAME}] StatusIcon not embedded after timeout, falling back to AppIndicator...", file=sys.stderr)
                    self.status_icon.set_visible(False)
                    self.status_icon = None
                    self._fallback_to_appindicator(tooltip)
                return False
            GLib.timeout_add(1500, _check_embedded)
            return True
        except Exception:
            return False

    def _fallback_to_appindicator(self, tooltip: str):
        for libname in ('AyatanaAppIndicator3', 'AppIndicator3'):
            try:
                gi.require_version(libname, '0.1')
                mod = __import__('gi.repository.' + libname, fromlist=[libname])
                self._setup_appindicator(mod, tooltip)
                print(f"[{APP_NAME}] Tray icon fallback to {libname} succeeded", file=sys.stderr)
                break
            except Exception:
                pass

    def _on_left_click(self, icon):
        success, screen, area, orientation = icon.get_geometry()
        print(f"[{APP_NAME}] StatusIcon activate (left-click)! geom success={success}, area=({getattr(area, 'x', None)}, {getattr(area, 'y', None)}, {getattr(area, 'width', None)}, {getattr(area, 'height', None)})", file=sys.stderr)
        if success:
            x = area.x + area.width // 2
            y = area.y + area.height + 4 if area.y < 100 else area.y - 4
            self.popup.toggle_at(x, y)
        else:
            self._on_remote_toggle()

    @staticmethod
    def apply_display_color_contrast(monitor: MonitorInfo, contrast: int | None = None,
                                     color_temp: int | None = None) -> bool:
        """Atomically and independently apply contrast and color temperature for this specific monitor.
        Uses xrandr --output <output_name> to ensure strict per-display isolation."""
        if contrast is not None:
            monitor.current_contrast = max(0, min(100, int(contrast)))
        if color_temp is not None:
            monitor.current_color_temp = max(COLOR_TEMP_MIN, min(COLOR_TEMP_MAX, int(color_temp)))

        c = monitor.current_contrast
        t = monitor.current_color_temp

        # 1. Hardware contrast for external DDC/CI monitor
        if not monitor.is_internal and isinstance(monitor.contrast, DDCController):
            try:
                monitor.contrast.set_value(c)
            except Exception as e:
                print(f"[{APP_NAME}] Error setting DDC contrast for {monitor.name}: {e}", file=sys.stderr)

        # 2. Per-output gamma for color temperature and software contrast
        if monitor.output_name:
            r_temp, g_temp, b_temp = kelvin_to_rgb(t)

            if monitor.is_internal or not isinstance(monitor.contrast, DDCController):
                # Internal or software display: apply contrast as gamma scaling (50% = normal 1.0)
                contrast_factor = 0.5 + (c / 100.0)
                r = max(0.1, min(3.0, r_temp * contrast_factor))
                g = max(0.1, min(3.0, g_temp * contrast_factor))
                b = max(0.1, min(3.0, b_temp * contrast_factor))
            else:
                # External DDC display: hardware contrast already set via DDC VCP 12,
                # so GPU gamma only applies the isolated color temperature.
                r, g, b = r_temp, g_temp, b_temp

            try:
                cmd = ["xrandr", "--output", monitor.output_name,
                       "--gamma", f"{r:.3f}:{g:.3f}:{b:.3f}"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                return res.returncode == 0
            except Exception as e:
                print(f"[{APP_NAME}] Error setting gamma on {monitor.output_name}: {e}", file=sys.stderr)
        return False

    @staticmethod
    def _apply_color_temp_for_monitor(monitor: MonitorInfo, temp: int) -> bool:
        return TrayApp.apply_display_color_contrast(monitor, color_temp=temp)

    def _on_contrast(self, monitor: MonitorInfo, contrast: int):
        def _do():
            TrayApp.apply_display_color_contrast(monitor, contrast=contrast)
        threading.Thread(target=_do, daemon=True).start()

    def _on_color_temp(self, monitor: MonitorInfo, temp: int):
        def _do():
            TrayApp.apply_display_color_contrast(monitor, color_temp=temp)
        threading.Thread(target=_do, daemon=True).start()

    def _apply_master_color_temp(self, temp: int):
        for mg in self.popup._monitor_groups:
            mg.set_color_temp(temp)
        if self.popup._master_group:
            self.popup._master_group.set_color_temp(temp)
        def _do():
            for m in self.monitors:
                TrayApp.apply_display_color_contrast(m, color_temp=temp)
            self._save_current_state()
        threading.Thread(target=_do, daemon=True).start()

    def _on_apply_preset(self, widget, preset_index):
        if 0 <= preset_index < len(self.presets):
            preset = self.presets[preset_index]
            br = preset.get("brightness", 100)
            co = preset.get("contrast", 50)
            ct = preset.get("color_temp", COLOR_TEMP_NEUTRAL)
            self.popup.update_all(brightness=br, contrast=co, color_temp=ct)
            def _do():
                for m in self.monitors:
                    m.brightness.set_value(br)
                    m.current_brightness = br
                    TrayApp.apply_display_color_contrast(m, contrast=co, color_temp=ct)
                self._save_current_state()
            threading.Thread(target=_do, daemon=True).start()

    def _on_toggle_night_mode(self, widget):
        self._night_mode_active = not self._night_mode_active
        if self._night_mode_active:
            self._saved_daylight_state = [
                (m, m.current_brightness, m.current_contrast, m.current_color_temp)
                for m in self.monitors
            ]
            nm_temp = self.config.get("night_mode_temp", 2700)
            nm_br = self.config.get("night_mode_brightness", 35)
            self.popup.update_all(brightness=nm_br, color_temp=nm_temp)
            def _do():
                for m in self.monitors:
                    m.brightness.set_value(nm_br)
                    m.current_brightness = nm_br
                    TrayApp.apply_display_color_contrast(m, color_temp=nm_temp)
                self._save_current_state()
            threading.Thread(target=_do, daemon=True).start()
        else:
            if self._saved_daylight_state:
                def _do():
                    for mon, br, co, ct in self._saved_daylight_state:
                        mon.brightness.set_value(br)
                        mon.current_brightness = br
                        TrayApp.apply_display_color_contrast(mon, contrast=co, color_temp=ct)
                    self._save_current_state()
                threading.Thread(target=_do, daemon=True).start()

    def _dim_monitor(self, target_mon: MonitorInfo):
        def _do():
            target_mon.brightness.set_value(5)
            target_mon.current_brightness = 5
            self._save_current_state()
            GLib.idle_add(self.popup.refresh_value)
        threading.Thread(target=_do, daemon=True).start()

    def _reset_all_displays(self):
        self.popup.update_all(brightness=100, contrast=75, color_temp=COLOR_TEMP_NEUTRAL)
        def _do():
            for m in self.monitors:
                m.brightness.set_value(100)
                m.current_brightness = 100
                if m.contrast:
                    m.contrast.set_value(75)
                m.current_contrast = 75
                m.current_color_temp = COLOR_TEMP_NEUTRAL
                TrayApp.apply_display_color_contrast(m, contrast=75, color_temp=COLOR_TEMP_NEUTRAL)
            self._save_current_state()
        threading.Thread(target=_do, daemon=True).start()

    def _on_edit_config(self, widget):
        config_path = DEFAULT_CONFIG_PATH
        if not os.path.exists(config_path):
            os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(self.config, f, indent=2)
        subprocess.Popen(["xdg-open", config_path])

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        # 0. Quick Open item (for AppIndicator)
        item_open = Gtk.MenuItem(label=_("brightness_slider"))
        item_open.connect("activate", self._on_indicator_activate)
        menu.append(item_open)
        menu.append(Gtk.SeparatorMenuItem())

        # 1. Night Mode Toggle
        nm_label = _("daylight_mode") if self._night_mode_active else _("night_mode")
        item_nm = Gtk.MenuItem(label=nm_label)
        item_nm.connect("activate", self._on_toggle_night_mode)
        menu.append(item_nm)

        # 1b. Auto Day/Night Schedule Toggle
        sched_on = self.scheduler.is_enabled()
        d_t = self.config.get("day_time", "07:00")
        n_t = self.config.get("night_time", "19:00")
        curr_p = self.scheduler.get_period()
        tag = " [☀ Day]" if curr_p == "day" else " [🌙 Night]"
        item_auto = Gtk.CheckMenuItem(label=f"⏰ Auto Schedule ({d_t} – {n_t}){tag}")
        item_auto.set_active(sched_on)
        item_auto.connect("toggled", self._on_toggle_auto_schedule)
        menu.append(item_auto)
        menu.append(Gtk.SeparatorMenuItem())

        # 2. Presets submenu
        if self.presets:
            p_menu = Gtk.Menu()
            p_item = Gtk.MenuItem(label="📋 Presets")
            p_item.set_submenu(p_menu)
            for i, preset in enumerate(self.presets):
                label = f"{preset['name']}  (☀{preset['brightness']}%"
                if preset.get('contrast') is not None:
                    label += f" ◑{preset['contrast']}%"
                if preset.get('color_temp'):
                    label += f" 🌡{preset['color_temp']}K"
                label += ")"
                it = Gtk.MenuItem(label=label)
                it.connect("activate", self._on_apply_preset, i)
                p_menu.append(it)
            menu.append(p_item)

        # 3. Quick Color Temp Submenu
        ct_menu = Gtk.Menu()
        ct_parent = Gtk.MenuItem(label=_("quick_temps"))
        ct_parent.set_submenu(ct_menu)
        for temp, label_text in [
            (6500, "6500K — Daylight (Neutral)"),
            (5500, "5500K — Soft White"),
            (4500, "4500K — Warm White"),
            (3500, "3500K — Warm Amber"),
            (2700, "2700K — Cozy Night Light"),
            (2200, "2200K — Candlelight"),
        ]:
            it = Gtk.MenuItem(label=label_text)
            it.connect("activate", lambda w, t=temp: self._apply_master_color_temp(t))
            ct_menu.append(it)
        ct_menu.append(Gtk.SeparatorMenuItem())
        it_ct_reset = Gtk.MenuItem(label="Reset Color to 6500K")
        it_ct_reset.connect("activate", lambda w: self._apply_master_color_temp(COLOR_TEMP_NEUTRAL))
        ct_menu.append(it_ct_reset)
        menu.append(ct_parent)

        # 4. Display Actions Submenu
        if len(self.monitors) > 1:
            act_menu = Gtk.Menu()
            act_parent = Gtk.MenuItem(label=_("screen_actions"))
            act_parent.set_submenu(act_menu)
            for mon in self.monitors:
                tag = "Laptop" if mon.is_internal else (mon.name or mon.device)
                it_dim = Gtk.MenuItem(label=f"Dim {tag} to 5%")
                it_dim.connect("activate", lambda w, m=mon: self._dim_monitor(m))
                act_menu.append(it_dim)
            act_menu.append(Gtk.SeparatorMenuItem())
            it_res = Gtk.MenuItem(label=_("reset_all"))
            it_res.connect("activate", lambda w: self._reset_all_displays())
            act_menu.append(it_res)
            menu.append(act_parent)

        menu.append(Gtk.SeparatorMenuItem())

        # 5. Redshift controls
        if self._is_redshift_running():
            label = _("resume_redshift") if self._redshift_paused else _("pause_redshift")
            item_rs = Gtk.MenuItem(label=label)
            item_rs.connect("activate", self._on_toggle_redshift)
            menu.append(item_rs)
            menu.append(Gtk.SeparatorMenuItem())

        # 6. Settings & Refresh
        item_edit = Gtk.MenuItem(label=_("edit_config"))
        item_edit.connect("activate", self._on_edit_config)
        menu.append(item_edit)

        item_refresh = Gtk.MenuItem(label=_("refresh_monitors"))
        item_refresh.connect("activate", self._on_refresh_monitors)
        menu.append(item_refresh)
        menu.append(Gtk.SeparatorMenuItem())

        # 7. Quit
        item_quit = Gtk.MenuItem(label=_("quit"))
        item_quit.connect("activate", lambda w: Gtk.main_quit())
        menu.append(item_quit)

        menu.show_all()
        return menu

    def _on_right_click(self, icon, button, time):
        menu = self._build_menu()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, time)

    @staticmethod
    def _is_redshift_running() -> bool:
        try:
            result = subprocess.run(["pgrep", "-x", "redshift"], capture_output=True)
            return result.returncode == 0
        except Exception:
            return False

    def _on_toggle_redshift(self, widget):
        try:
            subprocess.run(["pkill", "-USR1", "redshift"], capture_output=True)
            self._redshift_paused = not self._redshift_paused
        except Exception:
            pass

    def _on_refresh_monitors(self, widget):
        print(f"[{APP_NAME}] Refreshing monitors...", file=sys.stderr)
        self._on_hotplug_detected()

    def _setup_appindicator(self, AppIndicatorLib, tooltip: str):
        theme = Gtk.IconTheme.get_default()
        icon_name = "display-brightness-symbolic" if theme.has_icon("display-brightness-symbolic") else "display-brightness"

        self.indicator = AppIndicatorLib.Indicator.new(
            APP_NAME,
            icon_name,
            AppIndicatorLib.IndicatorCategory.HARDWARE
        )
        if os.path.exists(self._icon_path):
            self.indicator.set_icon_theme_path(os.path.dirname(self._icon_path))
        self.indicator.set_status(AppIndicatorLib.IndicatorStatus.ACTIVE)
        self.indicator.set_title(tooltip)
        self.indicator.connect("scroll-event", self._on_indicator_scroll)

        menu = self._build_menu()
        self.indicator.set_menu(menu)

    def _on_indicator_activate(self, widget):
        self._on_remote_toggle()

    def _on_scroll_event(self, icon, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self._adjust_brightness(self.scroll_step)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self._adjust_brightness(-self.scroll_step)

    def _on_indicator_scroll(self, indicator, delta, direction):
        if direction == Gdk.ScrollDirection.UP:
            self._adjust_brightness(self.scroll_step)
        elif direction == Gdk.ScrollDirection.DOWN:
            self._adjust_brightness(-self.scroll_step)

    def _adjust_brightness(self, delta):
        if not self.monitors:
            return
        if self._cached_brightness is None:
            self._cached_brightness = self.monitors[0].brightness.get_value()
            if self._cached_brightness is None:
                self._cached_brightness = self.monitors[0].current_brightness
        new_val = max(self.min_val, min(self.max_val, self._cached_brightness + delta))
        if new_val == self._cached_brightness:
            return
        self._cached_brightness = new_val
        if self.popup._visible:
            self.popup.update_value(new_val)
        if self._scroll_debounce_id:
            GLib.source_remove(self._scroll_debounce_id)
        self._scroll_debounce_id = GLib.timeout_add(100, self._apply_scroll_brightness, new_val)

    def _apply_scroll_brightness(self, value):
        self._scroll_debounce_id = None
        def _set_all():
            for mon in self.monitors:
                mon.current_brightness = value
                mon.brightness.set_value(value)
            GLib.idle_add(self._save_current_state)
        threading.Thread(target=_set_all, daemon=True).start()
        return False


# ---------------------------------------------------------------------------
#  Standalone Window
# ---------------------------------------------------------------------------

class StandaloneWindow(Gtk.Window):

    def __init__(self, monitors: list[MonitorInfo], min_val: int, max_val: int, step: int,
                 cached_state: list[dict] | None = None, config: dict | None = None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title(_("window_title"))
        self.set_border_width(12)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", Gtk.main_quit)

        self.monitors = monitors
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.config = config or DEFAULT_CONFIG
        self._monitor_groups: list[_SliderGroup] = []
        self._master_group: _SliderGroup | None = None

        self._vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(self._vbox)

        self._populate_ui()

        if cached_state:
            self._apply_cached(cached_state)
            self._restore_color_temps(cached_state)
        self._refresh_async()

        # Display hotplug watcher
        self.hotplug_watcher = DisplayHotplugWatcher(self._on_hotplug_detected)

    def _on_hotplug_detected(self):
        def _bg():
            new_monitors = probe_all_monitors(
                vcp_brightness=VCP_BRIGHTNESS,
                vcp_contrast=VCP_CONTRAST,
                include_internal=self.config.get("include_internal_display", True),
                cached_state=load_state()
            )
            curr_keys = [(m.bus, m.output_name) for m in self.monitors]
            new_keys = [(m.bus, m.output_name) for m in new_monitors]
            if curr_keys != new_keys:
                GLib.idle_add(self._apply_monitors_update, new_monitors)
        threading.Thread(target=_bg, daemon=True).start()

    def _apply_monitors_update(self, new_monitors: list[MonitorInfo]):
        self.monitors = new_monitors
        self.rebuild_monitors(new_monitors)
        self._save_current_state()
        return False

    def _populate_ui(self):
        multi = len(self.monitors) > 1
        show_contrast = self.config.get("show_contrast_slider", True)
        show_ct = self.config.get("show_color_temp_slider", True)

        if multi:
            master_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self._vbox.pack_start(master_box, False, False, 0)
            self._master_group = _SliderGroup(
                master_box, None, self.min_val, self.max_val, self.step,
                on_brightness=self._on_master_brightness,
                on_contrast=self._on_master_contrast,
                show_presets=True,
                on_color_temp=self._on_master_color_temp,
                show_contrast=show_contrast,
                show_color_temp=show_ct)

        for mon in self.monitors:
            if multi:
                self._vbox.pack_start(Gtk.Separator(), False, False, 4)
                tag = "💻" if mon.is_internal else "🖥"
                header_text = f"{tag} {mon.name or mon.device}"
                header = Gtk.Label()
                header.set_markup(f"<b>{GLib.markup_escape_text(header_text)}</b>")
                header.set_xalign(0.0)
                self._vbox.pack_start(header, False, False, 0)

            mon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self._vbox.pack_start(mon_box, False, False, 0)
            group = _SliderGroup(
                mon_box, mon, self.min_val, self.max_val, self.step,
                on_brightness=self._on_monitor_brightness,
                on_contrast=self._on_monitor_contrast,
                show_presets=not multi,
                on_color_temp=self._on_monitor_color_temp,
                show_contrast=show_contrast,
                show_color_temp=show_ct)

            group.set_brightness(mon.current_brightness)
            if group.contrast_scale:
                group.set_contrast(mon.current_contrast)
            if group.color_temp_scale:
                group.set_color_temp(mon.current_color_temp)

            self._monitor_groups.append(group)

        self._sync_master()

    def rebuild_monitors(self, new_monitors: list[MonitorInfo]):
        self.monitors = new_monitors
        for child in self._vbox.get_children():
            self._vbox.remove(child)
        self._monitor_groups.clear()
        self._master_group = None
        self._populate_ui()
        self.show_all()

    def _restore_color_temps(self, cached_state: list[dict]):
        cache_map = {entry["bus"]: entry for entry in cached_state}
        targets = []
        for mon in self.monitors:
            entry = cache_map.get(mon.bus)
            if entry and entry.get("color_temp") and entry.get("color_temp") != COLOR_TEMP_NEUTRAL:
                targets.append((mon, entry["color_temp"]))
        if targets:
            def _do():
                for mon, ct in targets:
                    TrayApp.apply_display_color_contrast(mon, color_temp=ct)
            threading.Thread(target=_do, daemon=True).start()

    def _apply_cached(self, cached: list[dict]):
        cache_map = {entry["bus"]: entry for entry in cached}
        for group in self._monitor_groups:
            entry = cache_map.get(group.monitor.bus)
            if entry:
                group.set_brightness(entry.get("brightness", 50))
                if group.contrast_scale:
                    group.set_contrast(entry.get("contrast", 50))
                if group.color_temp_scale:
                    group.set_color_temp(entry.get("color_temp", COLOR_TEMP_NEUTRAL))
        self._sync_master()

    def _refresh_async(self):
        def _do_refresh():
            results = {}
            for group in self._monitor_groups:
                mon = group.monitor
                b = mon.brightness.get_value()
                c = mon.contrast.get_value() if group.contrast_scale else None
                results[mon.bus] = (b, c)
            GLib.idle_add(self._apply_hw_results, results)
        threading.Thread(target=_do_refresh, daemon=True).start()

    def _apply_hw_results(self, results: dict):
        for group in self._monitor_groups:
            vals = results.get(group.monitor.bus)
            if vals:
                b, c = vals
                if b is not None:
                    group.set_brightness(b)
                if c is not None and group.contrast_scale:
                    group.set_contrast(c)
        self._sync_master()
        return False

    def _sync_master(self):
        if self._master_group and self._monitor_groups:
            avg_b = sum(int(mg.brightness_scale.get_value()) for mg in self._monitor_groups) // len(self._monitor_groups)
            self._master_group.set_brightness(avg_b)
            if self._master_group.contrast_scale:
                c_groups = [mg for mg in self._monitor_groups if mg.contrast_scale]
                if c_groups:
                    avg_c = sum(int(mg.contrast_scale.get_value()) for mg in c_groups) // len(c_groups)
                    self._master_group.set_contrast(avg_c)
            if self._master_group.color_temp_scale:
                ct_groups = [mg for mg in self._monitor_groups if mg.color_temp_scale]
                if ct_groups:
                    avg_ct = sum(int(mg.color_temp_scale.get_value()) for mg in ct_groups) // len(ct_groups)
                    self._master_group.set_color_temp(avg_ct)

    def _on_monitor_brightness(self, group: _SliderGroup, value: int):
        if group.monitor is not None:
            group.monitor.current_brightness = value
            threading.Thread(target=group.monitor.brightness.set_value, args=(value,), daemon=True).start()
        self._sync_master()
        self._save_current_state()

    def _on_monitor_contrast(self, group: _SliderGroup, value: int):
        if group.monitor is not None:
            group.monitor.current_contrast = value
            threading.Thread(target=TrayApp.apply_display_color_contrast,
                             args=(group.monitor, value, None), daemon=True).start()
        self._sync_master()
        self._save_current_state()

    def _on_master_brightness(self, group: _SliderGroup, value: int):
        for mg in self._monitor_groups:
            mg.set_brightness(value)
            if mg.monitor is not None:
                mg.monitor.current_brightness = value
        def _do():
            for mg in self._monitor_groups:
                if mg.monitor is not None:
                    mg.monitor.brightness.set_value(value)
        threading.Thread(target=_do, daemon=True).start()
        self._save_current_state()

    def _on_master_contrast(self, group: _SliderGroup, value: int):
        for mg in self._monitor_groups:
            mg.set_contrast(value)
            if mg.monitor is not None:
                mg.monitor.current_contrast = value
        def _do():
            for mg in self._monitor_groups:
                if mg.monitor is not None:
                    TrayApp.apply_display_color_contrast(mg.monitor, contrast=value)
        threading.Thread(target=_do, daemon=True).start()
        self._save_current_state()

    def _on_monitor_color_temp(self, group: _SliderGroup, value: int):
        if group.monitor is not None:
            group.monitor.current_color_temp = value
            threading.Thread(target=TrayApp.apply_display_color_contrast,
                             args=(group.monitor, None, value), daemon=True).start()
        self._sync_master()
        self._save_current_state()

    def _on_master_color_temp(self, group: _SliderGroup, value: int):
        for mg in self._monitor_groups:
            mg.set_color_temp(value)
            if mg.monitor is not None:
                mg.monitor.current_color_temp = value
        def _do():
            for mg in self._monitor_groups:
                if mg.monitor is not None:
                    TrayApp.apply_display_color_contrast(mg.monitor, color_temp=value)
        threading.Thread(target=_do, daemon=True).start()
        self._save_current_state()

    def _save_current_state(self):
        values = {}
        for group in self._monitor_groups:
            mon = group.monitor
            if mon is None:
                continue
            entry = {
                "brightness": int(group.brightness_scale.get_value()),
                "contrast": int(group.contrast_scale.get_value()) if group.contrast_scale else 50,
            }
            if group.color_temp_scale is not None:
                entry["color_temp"] = int(group.color_temp_scale.get_value())
            values[mon.bus] = entry
        save_state(self.monitors, values)


# ---------------------------------------------------------------------------
#  Main entrypoint & CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Universal Display Brightness, Contrast & Color Temp Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Examples:
  %(prog)s                          # Tray icon mode (default) / toggle if running
  %(prog)s --list                   # List all detected displays
  %(prog)s --get                    # Print current brightness of all displays
  %(prog)s --set 70                 # Set brightness to 70%% on all displays
  %(prog)s --output eDP-1 --set 50  # Set brightness to 50%% on eDP-1
  %(prog)s --temp 3000              # Set color temperature to 3000K
  %(prog)s --toggle-night           # Toggle Night Mode on/off
  %(prog)s --reset                  # Reset displays to 100%% brightness & 6500K
  %(prog)s --standalone             # Floating window mode

Config: {DEFAULT_CONFIG_PATH}
State:  {DEFAULT_STATE_PATH}
"""
    )
    parser.add_argument("-v", "-V", "--version", action="version",
                        version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("-b", "--bus", type=int, default=None,
                        help="Specific I2C bus number")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Target specific output connector (e.g. eDP-1, HDMI-1)")
    parser.add_argument("--min", type=int, default=DEFAULT_MIN,
                        help=f"Minimum brightness value (default: {DEFAULT_MIN})")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX,
                        help=f"Maximum brightness value (default: {DEFAULT_MAX})")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP,
                        help=f"Slider step size (default: {DEFAULT_STEP})")
    parser.add_argument("--scroll-step", type=int, default=None,
                        help=f"Scroll step size (default: {DEFAULT_SCROLL_STEP})")
    parser.add_argument("--standalone", action="store_true",
                        help="Show as a floating window instead of tray icon")
    parser.add_argument("--list", action="store_true",
                        help="List all detected screens and exit")
    parser.add_argument("--set", type=int, metavar="VALUE",
                        help="Set brightness to VALUE (0-100) and exit")
    parser.add_argument("--get", action="store_true",
                        help="Print current brightness and exit")
    parser.add_argument("--set-contrast", type=int, metavar="VALUE",
                        help="Set contrast to VALUE (0-100) and exit")
    parser.add_argument("--get-contrast", action="store_true",
                        help="Print current contrast and exit")
    parser.add_argument("--temp", type=int, metavar="KELVIN",
                        help="Set color temperature in Kelvin (e.g. 2700, 3500, 6500) and exit")
    parser.add_argument("--toggle-night", action="store_true",
                        help="Toggle Night Mode (warm kelvin + dimmed brightness) and exit")
    parser.add_argument("--day", action="store_true",
                        help="Switch all displays to Day Mode (6500K, 100%% brightness) and exit")
    parser.add_argument("--night", action="store_true",
                        help="Switch all displays to Night Mode (2700K, 35%% brightness) and exit")
    parser.add_argument("--auto-schedule", choices=["on", "off", "status"], nargs="?", const="status",
                        help="Query or configure automatic Day/Night schedule ('on', 'off', or 'status') and exit")
    parser.add_argument("--reset", action="store_true",
                        help="Reset all screens to neutral (100%% brightness, 6500K) and exit")
    parser.add_argument("--no-internal", action="store_true",
                        help="Exclude laptop internal display")
    parser.add_argument("--config", metavar="FILE",
                        help=f"JSON config file (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--no-config", action="store_true",
                        help="Disable config file loading")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip state cache, force full hardware probe")
    parser.add_argument("--icon", choices=["light", "dark", "auto"], default="auto",
                        help="Tray icon color (default: auto)")

    args = parser.parse_args()

    # Check if CLI action was requested
    is_cli_action = any([
        args.list, args.get, args.get_contrast,
        args.set is not None, args.set_contrast is not None,
        args.temp is not None, args.toggle_night, args.reset,
        args.day, args.night, args.auto_schedule is not None
    ])

    # If running GUI mode and already running, send IPC message to toggle popup and exit
    if not args.standalone and not is_cli_action:
        if send_toggle_to_running_instance():
            print(f"[{APP_NAME}] ddc-slider is already running; toggled brightness popup.", file=sys.stderr)
            sys.exit(0)

    # Load config
    config = DEFAULT_CONFIG.copy()
    if not args.no_config:
        config_path = args.config or DEFAULT_CONFIG_PATH
        if not os.path.exists(config_path) and not args.config:
            os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        if os.path.exists(config_path):
            config = load_config(config_path)

    include_internal = config.get("include_internal_display", True) and not args.no_internal

    # Build monitor list
    cached_state = None
    if args.bus is not None:
        monitors = [MonitorInfo(
            bus=args.bus, device=f"/dev/i2c-{args.bus}",
            name=f"Monitor (bus {args.bus})",
            brightness=DDCController(args.bus, VCP_BRIGHTNESS),
            contrast=DDCController(args.bus, VCP_CONTRAST),
            is_internal=False
        )]
    else:
        if not args.no_cache and not args.list:
            cached_state = load_state()

        monitors = None
        if cached_state:
            monitors = fast_build_from_cache(cached_state, VCP_BRIGHTNESS, VCP_CONTRAST,
                                            include_internal=include_internal)
        if not monitors:
            monitors = probe_all_monitors(VCP_BRIGHTNESS, VCP_CONTRAST,
                                         include_internal=include_internal,
                                         cached_state=cached_state)

    if not monitors:
        print(f"[{APP_NAME}] ERROR: No screens detected.", file=sys.stderr)
        sys.exit(1)

    # Filter target monitor if --output specified
    target_monitors = monitors
    if args.output:
        filtered = [m for m in monitors if m.output_name and m.output_name.lower() == args.output.lower()]
        if filtered:
            target_monitors = filtered
        else:
            print(f"[{APP_NAME}] Warning: output '{args.output}' not found among {[m.output_name for m in monitors]}",
                  file=sys.stderr)

    # --- CLI Actions ---
    if args.list:
        print(f"Detected {len(monitors)} display(s):")
        for i, m in enumerate(monitors):
            m_type = "Internal Laptop Screen" if m.is_internal else "External DDC/CI Screen"
            out = m.output_name or "unknown"
            crtc = f"crtc={m.crtc_index}" if m.crtc_index is not None else "no crtc"
            print(f"  [{i+1}] {m.name} | {m_type} | output: {out} ({crtc}) | device: {m.device}")
        sys.exit(0)

    if args.get:
        out_strs = []
        for m in target_monitors:
            val = m.brightness.get_value()
            tag = m.output_name or m.name
            out_strs.append(f"{tag}: {val}%")
        print(", ".join(out_strs))
        sys.exit(0)

    if args.get_contrast:
        out_strs = []
        for m in target_monitors:
            val = m.contrast.get_value() if m.contrast else None
            tag = m.output_name or m.name
            out_strs.append(f"{tag}: {val}%" if val is not None else f"{tag}: N/A")
        print(", ".join(out_strs))
        sys.exit(0)

    if args.set is not None:
        for m in target_monitors:
            m.brightness.set_value(args.set)
            m.current_brightness = args.set
        save_state(monitors, {m.bus: {"brightness": m.current_brightness, "contrast": m.current_contrast, "color_temp": m.current_color_temp} for m in monitors})
        sys.exit(0)

    if args.set_contrast is not None:
        for m in target_monitors:
            TrayApp.apply_display_color_contrast(m, contrast=args.set_contrast)
        save_state(monitors, {m.bus: {"brightness": m.current_brightness, "contrast": args.set_contrast, "color_temp": m.current_color_temp} for m in monitors})
        sys.exit(0)

    if args.temp is not None:
        for m in target_monitors:
            TrayApp.apply_display_color_contrast(m, color_temp=args.temp)
        save_state(monitors, {m.bus: {"brightness": m.current_brightness, "contrast": m.current_contrast, "color_temp": args.temp} for m in monitors})
        sys.exit(0)

    if args.reset:
        for m in monitors:
            m.brightness.set_value(100)
            m.current_brightness = 100
            if m.contrast:
                m.contrast.set_value(75)
            m.current_contrast = 75
            m.current_color_temp = COLOR_TEMP_NEUTRAL
            TrayApp.apply_display_color_contrast(m, contrast=75, color_temp=COLOR_TEMP_NEUTRAL)
        save_state(monitors, {m.bus: {"brightness": 100, "contrast": 75, "color_temp": COLOR_TEMP_NEUTRAL} for m in monitors})
        print(f"[{APP_NAME}] All displays reset to 100%% brightness, 75%% contrast, 6500K neutral.")
        sys.exit(0)

    if args.day:
        if send_ipc_message(b"day\n"):
            print(f"[{APP_NAME}] Switched running instance to Day Mode.")
            sys.exit(0)
        d_br = config.get("day_mode_brightness", 100)
        d_co = config.get("day_mode_contrast", 75)
        d_ct = config.get("day_mode_temp", 6500)
        for m in monitors:
            m.brightness.set_value(d_br)
            m.current_brightness = d_br
            TrayApp.apply_display_color_contrast(m, contrast=d_co, color_temp=d_ct)
        save_state(monitors, {m.bus: {"brightness": d_br, "contrast": d_co, "color_temp": d_ct} for m in monitors})
        print(f"[{APP_NAME}] Switched to Day Mode ({d_br}% / {d_ct}K)")
        sys.exit(0)

    if args.night:
        if send_ipc_message(b"night\n"):
            print(f"[{APP_NAME}] Switched running instance to Night Mode.")
            sys.exit(0)
        n_br = config.get("night_mode_brightness", 35)
        n_co = config.get("night_mode_contrast", 50)
        n_ct = config.get("night_mode_temp", 2700)
        for m in monitors:
            m.brightness.set_value(n_br)
            m.current_brightness = n_br
            TrayApp.apply_display_color_contrast(m, contrast=n_co, color_temp=n_ct)
        save_state(monitors, {m.bus: {"brightness": n_br, "contrast": n_co, "color_temp": n_ct} for m in monitors})
        print(f"[{APP_NAME}] Switched to Night Mode ({n_br}% / {n_ct}K)")
        sys.exit(0)

    if args.auto_schedule is not None:
        if args.auto_schedule == "status":
            sched_on = config.get("auto_schedule_enabled", True)
            d_t = config.get("day_time", "07:00")
            n_t = config.get("night_time", "19:00")
            p = get_current_period(d_t, n_t)
            print(f"Auto Day/Night Schedule: {'ENABLED' if sched_on else 'DISABLED'}")
            print(f"  Day Time:   {d_t} -> {config.get('day_mode_brightness', 100)}% brightness, {config.get('day_mode_temp', 6500)}K")
            print(f"  Night Time: {n_t} -> {config.get('night_mode_brightness', 35)}% brightness, {config.get('night_mode_temp', 2700)}K")
            print(f"  Current:    {p.upper()} mode")
            sys.exit(0)
        elif args.auto_schedule == "on":
            send_ipc_message(b"auto_on\n")
            config["auto_schedule_enabled"] = True
            save_config_file(config)
            print(f"[{APP_NAME}] Auto Day/Night schedule enabled.")
            sys.exit(0)
        elif args.auto_schedule == "off":
            send_ipc_message(b"auto_off\n")
            config["auto_schedule_enabled"] = False
            save_config_file(config)
            print(f"[{APP_NAME}] Auto Day/Night schedule disabled.")
            sys.exit(0)

    if args.toggle_night:
        if send_ipc_message(b"toggle_night\n"):
            print(f"[{APP_NAME}] Toggled Night Mode on running instance.")
            sys.exit(0)
        state = load_state() or []
        first_temp = state[0].get("color_temp", COLOR_TEMP_NEUTRAL) if state else COLOR_TEMP_NEUTRAL
        if first_temp < 5000:
            for m in monitors:
                m.brightness.set_value(100)
                m.current_brightness = 100
                TrayApp.apply_display_color_contrast(m, contrast=75, color_temp=COLOR_TEMP_NEUTRAL)
            save_state(monitors, {m.bus: {"brightness": 100, "contrast": 75, "color_temp": COLOR_TEMP_NEUTRAL} for m in monitors})
            print(f"[{APP_NAME}] Switched to Daylight Mode (100%% / 6500K)")
        else:
            nm_temp = config.get("night_mode_temp", 2700)
            nm_br = config.get("night_mode_brightness", 35)
            for m in monitors:
                m.brightness.set_value(nm_br)
                m.current_brightness = nm_br
                TrayApp.apply_display_color_contrast(m, color_temp=nm_temp)
            save_state(monitors, {m.bus: {"brightness": nm_br, "contrast": 50, "color_temp": nm_temp} for m in monitors})
            print(f"[{APP_NAME}] Switched to Night Mode ({nm_br}%% / {nm_temp}K)")
        sys.exit(0)

    # --- GUI Mode ---
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    scroll_step = args.scroll_step if args.scroll_step is not None else config.get("scroll_step", DEFAULT_SCROLL_STEP)

    if args.standalone:
        win = StandaloneWindow(monitors, args.min, args.max, args.step,
                               cached_state=cached_state, config=config)
        win.show_all()
    else:
        icon_style = None if args.icon == "auto" else args.icon
        app = TrayApp(monitors, args.min, args.max, args.step,
                      scroll_step=scroll_step, config=config,
                      cached_state=cached_state, icon_style=icon_style,
                      original_cmd=sys.argv[0])

    Gtk.main()


if __name__ == "__main__":
    main()
