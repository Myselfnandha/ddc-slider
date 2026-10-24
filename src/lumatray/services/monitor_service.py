"""
Monitor discovery, persistent identity management, and live hotplug detection.
"""

from __future__ import annotations

import glob
import hashlib
import logging
import os
import re
import subprocess
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from ..core.events import EventType, events
from ..core.models import DisplayIdentity, DisplayType

logger = logging.getLogger(__name__)


def _xrandr_outputs() -> Dict[str, Optional[int]]:
    """Return dict of connected XRandR output names -> crtc_index."""
    outputs: Dict[str, Optional[int]] = {}
    try:
        res = subprocess.run(["xrandr", "--verbose"], capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return outputs
        cur_out = None
        cur_crtc = None
        for line in res.stdout.splitlines():
            m_conn = re.match(r"^(\S+)\s+connected(?:\s+primary)?(?:\s+(\d+x\d+\+\d+\+\d+))?", line)
            if m_conn:
                if cur_out:
                    outputs[cur_out] = cur_crtc
                cur_out = m_conn.group(1)
                cur_crtc = None
                continue
            if cur_out and re.match(r"^\S+\s+disconnected", line):
                outputs[cur_out] = cur_crtc
                cur_out = None
                cur_crtc = None
                continue
            if cur_out and "CRTC:" in line:
                m_c = re.search(r"CRTC:\s*(\d+)", line)
                if m_c:
                    cur_crtc = int(m_c.group(1))
        if cur_out:
            outputs[cur_out] = cur_crtc
    except Exception as e:
        logger.debug(f"Error executing xrandr --verbose: {e}")
    return outputs


def _get_drm_connector_for_bus(bus: int) -> Optional[str]:
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
                m = re.search(r"i2c-(\d+)", target)
                if m and int(m.group(1)) == bus:
                    conn = re.sub(r"^card\d+-", "", entry)
                    return conn
            except OSError:
                continue
    return None


class MonitorService:
    """Manages monitor discovery, identity persistence, and hotplug monitoring."""

    def __init__(self):
        self._monitors: List[DisplayIdentity] = []
        self._lock = threading.RLock()
        self._hotplug_watcher: Optional[threading.Thread] = None
        self._watcher_running = False
        self._remembered_states: Dict[str, dict] = {}


    def discover_monitors(self) -> List[DisplayIdentity]:
        """Perform a full hardware probe of all connected displays."""
        displays: List[DisplayIdentity] = []
        claimed_outputs: Set[str] = set()
        x_outs = _xrandr_outputs()

        # 1. Internal laptop panels
        for bl in glob.glob("/sys/class/backlight/*"):
            # Find matching internal connector (eDP, LVDS, DSI)
            conn_name = None
            crtc_idx = None
            for out_name, c_idx in x_outs.items():
                if re.match(r"^(eDP|LVDS|DSI)", out_name, re.IGNORECASE):
                    conn_name = out_name
                    crtc_idx = c_idx
                    claimed_outputs.add(out_name)
                    break

            disp_id = f"internal_{os.path.basename(bl)}"
            displays.append(DisplayIdentity(
                id=disp_id,
                name="Built-in Display",
                display_type=DisplayType.INTERNAL_BACKLIGHT,
                bus=-1,
                device_path=bl,
                connector_name=conn_name,
                crtc_index=crtc_idx,
                is_internal=True,
            ))
            break  # Typically single internal panel

        # 2. External DDC/CI monitors
        try:
            res = subprocess.run(["ddcutil", "detect", "--brief"], capture_output=True, text=True, timeout=10)
            bus = None
            model = ""
            mfg = ""
            serial = ""
            edid_hex = ""
            valid = False

            def _commit_ddc(b, m, mf, s, eh):
                if b is not None and b > 0:
                    conn = _get_drm_connector_for_bus(b)
                    crtc = None
                    if conn:
                        # Match DRM connector to XRandR output
                        for x_name, c_idx in x_outs.items():
                            if x_name == conn or x_name.replace("-", "") == conn.replace("-", "") or x_name in conn or conn in x_name:
                                conn = x_name
                                crtc = c_idx
                                claimed_outputs.add(x_name)
                                break
                    disp_hash = hashlib.sha256(f"{mf}:{m}:{s}:{b}".encode()).hexdigest()[:12]
                    disp_id = f"ddc_{disp_hash}"
                    name = m or f"External Monitor (bus {b})"
                    displays.append(DisplayIdentity(
                        id=disp_id,
                        name=name,
                        display_type=DisplayType.EXTERNAL_DDC,
                        bus=b,
                        device_path=f"/dev/i2c-{b}",
                        connector_name=conn,
                        crtc_index=crtc,
                        manufacturer=mf,
                        model=m,
                        serial=s,
                        edid_hash=disp_hash,
                        is_internal=False,
                    ))

            for line in res.stdout.splitlines():
                if re.match(r"^Display\s+\d+", line):
                    if bus is not None and valid:
                        _commit_ddc(bus, model, mfg, serial, edid_hex)
                    bus, model, mfg, serial, edid_hex = None, "", "", "", ""
                    valid = True
                elif re.match(r"^Invalid display", line):
                    if bus is not None and valid:
                        _commit_ddc(bus, model, mfg, serial, edid_hex)
                    bus, model, mfg, serial, edid_hex = None, "", "", "", ""
                    valid = False

                m_bus = re.search(r"I2C bus:\s*/dev/i2c-(\d+)", line)
                if m_bus:
                    bus = int(m_bus.group(1))
                m_model = re.search(r"(?:Model|Monitor):\s*(.+)", line)
                if m_model:
                    model = m_model.group(1).strip()
                m_mfg = re.search(r"Mfg:\s*(.+)", line)
                if m_mfg:
                    mfg = m_mfg.group(1).strip()
                m_sn = re.search(r"Serial number:\s*(.+)", line)
                if m_sn:
                    serial = m_sn.group(1).strip()

            if bus is not None and valid:
                _commit_ddc(bus, model, mfg, serial, edid_hex)
        except Exception as e:
            logger.warning(f"Error running ddcutil detect: {e}")

        # 3. External displays detected by XRandR without DDC response
        ext_outs = [name for name in x_outs.keys() if not re.match(r"^(eDP|LVDS|DSI)", name, re.IGNORECASE)]
        for idx, out_name in enumerate(ext_outs):
            if out_name not in claimed_outputs:
                claimed_outputs.add(out_name)
                vbus = -10 - idx
                displays.append(DisplayIdentity(
                    id=f"soft_{out_name}",
                    name=f"Display ({out_name})",
                    display_type=DisplayType.EXTERNAL_SOFTWARE,
                    bus=vbus,
                    device_path=out_name,
                    connector_name=out_name,
                    crtc_index=x_outs.get(out_name),
                    is_internal=False,
                ))

        with self._lock:
            self._monitors = displays

        events.emit(EventType.MONITORS_CHANGED, monitors=displays)
        return displays

    def get_monitors(self) -> List[DisplayIdentity]:
        with self._lock:
            if self._monitors:
                return list(self._monitors)
        return self.discover_monitors()


    def get_monitor_by_id(self, display_id: str) -> Optional[DisplayIdentity]:
        for m in self.get_monitors():
            if m.id == display_id:
                return m
        return None

    def start_hotplug_watcher(self) -> None:
        """Start background polling thread to detect display connection and disconnection."""
        if self._watcher_running:
            return
        self._watcher_running = True
        self._hotplug_watcher = threading.Thread(target=self._hotplug_loop, name="HotplugWatcher", daemon=True)
        self._hotplug_watcher.start()

    def stop_hotplug_watcher(self) -> None:
        self._watcher_running = False

    def _hotplug_loop(self) -> None:
        """Watch DRM connector statuses for hotplug changes."""
        last_signature = self._get_drm_signature()
        while self._watcher_running:
            time.sleep(2.0)
            try:
                cur_signature = self._get_drm_signature()
                if cur_signature != last_signature:
                    logger.info("Display hotplug event detected! Re-probing monitors...")
                    time.sleep(1.5)  # Wait for kernel & X11 modesetting to settle
                    last_signature = self._get_drm_signature()
                    self.discover_monitors()
            except Exception as e:
                logger.debug(f"Error in hotplug watcher loop: {e}")

    @staticmethod
    def _get_drm_signature() -> str:
        statuses = []
        for path in sorted(glob.glob("/sys/class/drm/card*-*/status")):
            try:
                with open(path, "r") as f:
                    statuses.append(f"{path}:{f.read().strip()}")
            except Exception:
                pass
        return ";".join(statuses)


# Global singleton instance
monitor_service = MonitorService()
