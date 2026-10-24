"""
Typed domain models for LumaTray.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class DisplayType(str, Enum):
    INTERNAL_BACKLIGHT = "internal_backlight"
    EXTERNAL_DDC = "external_ddc"
    EXTERNAL_SOFTWARE = "external_software"
    VIRTUAL = "virtual"


@dataclasses.dataclass
class DisplayIdentity:
    """Stable, persistent identity for a display across reconnects."""
    id: str                               # Unique stable identifier
    name: str                             # User-friendly label
    display_type: DisplayType             # Display backend type
    bus: int                              # I2C bus (>0) or virtual/backlight index (<0)
    device_path: str                      # /dev/i2c-X or /sys/class/backlight/...
    connector_name: Optional[str] = None  # e.g. eDP-1, HDMI-A-1, DP-1
    crtc_index: Optional[int] = None      # X11 CRTC index if known
    manufacturer: str = ""
    model: str = ""
    serial: str = ""
    edid_hash: str = ""
    is_internal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_type": self.display_type.value,
            "bus": self.bus,
            "device_path": self.device_path,
            "connector_name": self.connector_name,
            "crtc_index": self.crtc_index,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "edid_hash": self.edid_hash,
            "is_internal": self.is_internal,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisplayIdentity:
        data = dict(data)
        data["display_type"] = DisplayType(data.get("display_type", DisplayType.EXTERNAL_DDC.value))
        return cls(**data)


@dataclasses.dataclass
class VCPFeature:
    """Represents a VCP feature supported by a monitor."""
    code: int                                 # VCP code (e.g. 0x10, 0x12)
    name: str                                 # Human-readable feature name
    is_continuous: bool = True                # Continuous slider vs discrete table
    min_value: int = 0
    max_value: int = 100
    current_value: Optional[int] = None
    supported_values: Dict[int, str] = dataclasses.field(default_factory=dict)
    read_only: bool = False

    @property
    def hex_code(self) -> str:
        return f"0x{self.code:02x}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "hex_code": self.hex_code,
            "name": self.name,
            "is_continuous": self.is_continuous,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "current_value": self.current_value,
            "supported_values": {str(k): v for k, v in self.supported_values.items()},
            "read_only": self.read_only,
        }


@dataclasses.dataclass
class CapabilityReport:
    """Hardware capability inspection report for a monitor."""
    display_id: str
    ddc_version: str = "2.0"
    features: Dict[int, VCPFeature] = dataclasses.field(default_factory=dict)
    raw_capabilities: str = ""
    timestamp: float = 0.0

    def supports(self, feature_code: int) -> bool:
        return feature_code in self.features

    def get_feature(self, feature_code: int) -> Optional[VCPFeature]:
        return self.features.get(feature_code)


@dataclasses.dataclass
class MonitorState:
    """Current live or target state of a monitor."""
    display_id: str
    brightness: int = 50
    contrast: int = 50
    color_temp: int = 6500                    # Kelvin (1000K-10000K)
    color_mode: str = "gamma"                 # "hardware", "gamma", "profile", "unsupported"
    rgb_gain: Tuple[int, int, int] = (100, 100, 100)  # Red, Green, Blue gains (0-100)
    preset: Optional[int] = None              # Discrete VCP 0x14 preset code
    input_source: Optional[int] = None        # VCP 0x60 input source code
    power_state: Optional[int] = None         # VCP 0xD6 power mode

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_id": self.display_id,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "color_temp": self.color_temp,
            "color_mode": self.color_mode,
            "rgb_gain": list(self.rgb_gain),
            "preset": self.preset,
            "input_source": self.input_source,
            "power_state": self.power_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MonitorState:
        data = dict(data)
        if "rgb_gain" in data and isinstance(data["rgb_gain"], list):
            data["rgb_gain"] = tuple(data["rgb_gain"][:3])
        return cls(**data)


@dataclasses.dataclass
class OperationResult:
    """Result of a hardware or software control operation."""
    success: bool
    verified: bool = False
    feature_code: Optional[int] = None
    requested_value: Any = None
    actual_value: Any = None
    error_message: Optional[str] = None
    latency_ms: float = 0.0


@dataclasses.dataclass
class Profile:
    """User or system defined monitor profile / scene."""
    id: str
    name: str
    icon: str = "display"
    description: str = ""
    monitors: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    master_brightness: int = 100
    master_contrast: int = 50
    master_color_temp: int = 6500
    is_system: bool = False
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "monitors": self.monitors,
            "master_brightness": self.master_brightness,
            "master_contrast": self.master_contrast,
            "master_color_temp": self.master_color_temp,
            "is_system": self.is_system,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        return cls(**data)


@dataclasses.dataclass
class AutomationRule:
    """Rule definition for automated transitions and scene changes."""
    id: str
    name: str
    trigger_type: str                         # "schedule", "ambient", "idle", "hotplug"
    priority: int = 10                        # Lower number = higher priority
    enabled: bool = True
    config: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "trigger_type": self.trigger_type,
            "priority": self.priority,
            "enabled": self.enabled,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationRule:
        return cls(**data)
