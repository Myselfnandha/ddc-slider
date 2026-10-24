"""
Capability Registry: inspects, parses, and caches hardware capabilities for monitors.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import Dict, Optional

from .models import CapabilityReport, DisplayIdentity, DisplayType, VCPFeature
from .validation import COLOR_PRESETS, INPUT_SOURCES, SAFE_VCP_ALLOWLIST

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """Registry that caches and queries monitor capabilities."""

    def __init__(self):
        self._cache: Dict[str, CapabilityReport] = {}

    def get_capabilities(
        self, display: DisplayIdentity, force_refresh: bool = False, fetch_hardware_capabilities: bool = False
    ) -> CapabilityReport:
        """Get or query capabilities for a display."""
        if not force_refresh and display.id in self._cache:
            # If cached report already has raw capabilities or hardware fetch not requested, return it
            cached = self._cache[display.id]
            if not fetch_hardware_capabilities or cached.raw_capabilities != "Standard DDC/CI (Default VCP)":
                return cached

        if display.display_type == DisplayType.INTERNAL_BACKLIGHT:
            report = self._build_internal_capabilities(display)
        elif display.display_type == DisplayType.EXTERNAL_DDC:
            report = self._query_ddc_capabilities(display, full_probe=fetch_hardware_capabilities)
        else:
            report = self._build_software_capabilities(display)

        self._cache[display.id] = report
        return report

    def _build_internal_capabilities(self, display: DisplayIdentity) -> CapabilityReport:
        features = {
            0x10: VCPFeature(code=0x10, name="Brightness", is_continuous=True, min_value=1, max_value=100),
            0x12: VCPFeature(code=0x12, name="Software Contrast (Gamma)", is_continuous=True, min_value=0, max_value=100),
        }
        return CapabilityReport(
            display_id=display.id,
            ddc_version="Internal Sysfs",
            features=features,
            raw_capabilities="Internal Panel (sysfs backlight + GPU gamma)",
            timestamp=time.time(),
        )

    def _build_software_capabilities(self, display: DisplayIdentity) -> CapabilityReport:
        features = {
            0x10: VCPFeature(code=0x10, name="Software Brightness", is_continuous=True, min_value=10, max_value=100),
            0x12: VCPFeature(code=0x12, name="Software Contrast (Gamma)", is_continuous=True, min_value=0, max_value=100),
        }
        return CapabilityReport(
            display_id=display.id,
            ddc_version="Software Fallback",
            features=features,
            raw_capabilities="GPU Gamma / XRandR Software Emulation",
            timestamp=time.time(),
        )

    def _query_ddc_capabilities(self, display: DisplayIdentity, full_probe: bool = False) -> CapabilityReport:
        """Query ddcutil capabilities for an external DDC/CI monitor."""
        features: Dict[int, VCPFeature] = {
            0x10: VCPFeature(code=0x10, name="Brightness", is_continuous=True, min_value=0, max_value=100),
            0x12: VCPFeature(code=0x12, name="Contrast", is_continuous=True, min_value=0, max_value=100),
            0x14: VCPFeature(code=0x14, name="Color Preset", is_continuous=False, supported_values=COLOR_PRESETS),
            0x16: VCPFeature(code=0x16, name="Red Video Gain", is_continuous=True, min_value=0, max_value=100),
            0x18: VCPFeature(code=0x18, name="Green Video Gain", is_continuous=True, min_value=0, max_value=100),
            0x1A: VCPFeature(code=0x1A, name="Blue Video Gain", is_continuous=True, min_value=0, max_value=100),
            0x60: VCPFeature(code=0x60, name="Input Source", is_continuous=False, supported_values=INPUT_SOURCES),
        }
        raw_output = "Standard DDC/CI (Default VCP)"
        ddc_version = "2.0"

        if full_probe:
            try:
                cmd = ["ddcutil", "capabilities", "--bus", str(display.bus)]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0 and res.stdout.strip():
                    raw_output = res.stdout
                    probed_features, ddc_version = self.parse_capabilities_string(raw_output)
                    if probed_features:
                        features.update(probed_features)
            except Exception as e:
                logger.warning(f"Could not query full capabilities for {display.name}: {e}")

        return CapabilityReport(
            display_id=display.id,
            ddc_version=ddc_version,
            features=features,
            raw_capabilities=raw_output,
            timestamp=time.time(),
        )


    @staticmethod
    def parse_capabilities_string(raw: str) -> tuple[Dict[int, VCPFeature], str]:
        """Parse raw ddcutil capabilities text into structured VCPFeatures."""
        features: Dict[int, VCPFeature] = {}
        ddc_version = "2.0"

        # Check for MCCS version
        mccs_match = re.search(r'mccs_ver(?:sion)?\s*\(([^)]+)\)', raw, re.IGNORECASE)
        if mccs_match:
            ddc_version = mccs_match.group(1)

        # Parse Feature entries
        # Format example: Feature: 10 (Brightness)
        # Format example: Feature: 14 (Color preset)
        #   Values: 01 02 04 05 06 08 0b
        # Format example: Feature: 60 (Input Source)
        #   Values: 0f 11 12
        for block in re.split(r'\n\s*Feature:\s*', raw):
            lines = block.strip().splitlines()
            if not lines:
                continue
            first_line = lines[0]
            header_match = re.match(r'^([0-9a-fA-F]{2})\s*(?:\(([^)]+)\))?', first_line)
            if not header_match:
                continue
            code = int(header_match.group(1), 16)
            name = header_match.group(2) or SAFE_VCP_ALLOWLIST.get(code, f"VCP 0x{code:02x}")

            # Check if there are discrete values specified
            supported_values: Dict[int, str] = {}
            is_continuous = True

            full_block_text = " ".join(lines[1:])
            val_match = re.search(r'Values:\s*([0-9a-fA-F\s]+)', full_block_text)
            if val_match:
                is_continuous = False
                tokens = val_match.group(1).split()
                for token in tokens:
                    try:
                        val_num = int(token, 16)
                        if code == 0x14:
                            val_label = COLOR_PRESETS.get(val_num, f"Preset 0x{val_num:02x}")
                        elif code == 0x60:
                            val_label = INPUT_SOURCES.get(val_num, f"Input 0x{val_num:02x}")
                        else:
                            val_label = f"Value 0x{val_num:02x}"
                        supported_values[val_num] = val_label
                    except ValueError:
                        continue

            features[code] = VCPFeature(
                code=code,
                name=name.strip(),
                is_continuous=is_continuous,
                min_value=0,
                max_value=100 if is_continuous else max(supported_values.keys(), default=1),
                supported_values=supported_values,
            )

        return features, ddc_version


# Global singleton instance
capability_registry = CapabilityRegistry()
