"""
Validation, safety rules, and VCP code allowlists for LumaTray.
"""

from __future__ import annotations

from typing import Any
from .errors import ValidationError

# Destructive VCP codes that MUST NEVER be called by generic sliders, presets or automation
DESTRUCTIVE_VCP_CODES = {
    0x04,  # Restore Factory Defaults
    0x05,  # Restore Brightness / Contrast
    0x06,  # Restore Geometry Defaults
    0x08,  # Restore Color Defaults
    0x0A,  # Restore Default On-Screen Display
}

# Standard safe VCP controls permitted in normal mode
SAFE_VCP_ALLOWLIST = {
    0x10: "Brightness",
    0x12: "Contrast",
    0x0C: "Color Temperature Request (Kelvin)",
    0x0B: "Color Temperature Increment",
    0x14: "Color Preset",
    0x16: "Red Video Gain",
    0x18: "Green Video Gain",
    0x1A: "Blue Video Gain",
    0x60: "Input Source",
    0x62: "Audio Speaker Volume",
    0xD6: "Power Control (DPMS)",
}

# Extended allowlist for opt-in Advanced Mode
EXTENDED_VCP_ALLOWLIST = {
    **SAFE_VCP_ALLOWLIST,
    0x1E: "Auto Setup",
    0x20: "Horizontal Position",
    0x30: "Vertical Position",
    0x8D: "Audio Mute",
    0xAA: "Screen Orientation",
}

# Known Color Presets (VCP 0x14)
COLOR_PRESETS = {
    0x01: "sRGB",
    0x02: "Display Native",
    0x03: "4000K",
    0x04: "5000K",
    0x05: "6500K",
    0x06: "7500K",
    0x07: "8200K",
    0x08: "9300K",
    0x09: "10000K",
    0x0A: "11500K",
    0x0B: "User 1",
    0x0C: "User 2",
    0x0D: "User 3",
}

# Known Input Sources (VCP 0x60)
INPUT_SOURCES = {
    0x01: "VGA-1",
    0x02: "VGA-2",
    0x03: "DVI-1",
    0x04: "DVI-2",
    0x05: "Composite-1",
    0x06: "Composite-2",
    0x07: "S-Video-1",
    0x08: "S-Video-2",
    0x09: "Tuner-1",
    0x0A: "Tuner-2",
    0x0B: "Component-1",
    0x0C: "Component-2",
    0x0D: "Component-3",
    0x0F: "DisplayPort-1",
    0x10: "DisplayPort-2",
    0x11: "HDMI-1",
    0x12: "HDMI-2",
    0x13: "USB-C",
}

# Power states (VCP 0xD6)
POWER_STATES = {
    0x01: "On / Active",
    0x02: "Standby",
    0x03: "Suspend",
    0x04: "Off",
    0x05: "Hard Power Off",
}


def is_destructive_vcp(vcp_code: int) -> bool:
    """Return True if the VCP code performs a destructive reset."""
    return vcp_code in DESTRUCTIVE_VCP_CODES


def clamp_value(val: int | float, min_val: int | float, max_val: int | float) -> int:
    """Clamp a numeric value to an integer within [min_val, max_val]."""
    return int(max(min_val, min(max_val, round(val))))


def clamp_brightness(val: int | float) -> int:
    """Brightness must be an integer between 0 and 100."""
    return clamp_value(val, 0, 100)


def clamp_contrast(val: int | float) -> int:
    """Contrast must be an integer between 0 and 100."""
    return clamp_value(val, 0, 100)


def clamp_kelvin(val: int | float) -> int:
    """Color temperature must be between 1000K and 10000K."""
    return clamp_value(val, 1000, 10000)


def clamp_rgb_gain(val: int | float) -> int:
    """RGB gains must be an integer between 0 and 100."""
    return clamp_value(val, 0, 100)


def validate_vcp_request(vcp_code: int, value: int, allow_extended: bool = False) -> None:
    """Validate that a VCP code and value are safe to execute."""
    if is_destructive_vcp(vcp_code):
        raise ValidationError(
            f"VCP code 0x{vcp_code:02x} is a destructive command (factory reset) and is strictly blocked."
        )

    allowed = EXTENDED_VCP_ALLOWLIST if allow_extended else SAFE_VCP_ALLOWLIST
    if vcp_code not in allowed:
        raise ValidationError(
            f"VCP code 0x{vcp_code:02x} is not in the recognized safe VCP allowlist."
        )

    if value < 0 or value > 65535:
        raise ValidationError(f"VCP value {value} is out of 16-bit range (0-65535).")
