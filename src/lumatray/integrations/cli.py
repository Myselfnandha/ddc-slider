"""
Command-line interface (CLI) for LumaTray.
Dispatches commands to a running instance via IPC or executes directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .. import __version__
from .dbus_service import send_ipc_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lumatray",
        description="LumaTray — Next-Generation GTK3 Monitor Control Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  lumatray --show                         Toggle quick brightness popup
  lumatray --list-monitors                List all detected displays & current values
  lumatray --set brightness 60            Set master brightness to 60%
  lumatray --set kelvin 4200              Set color temperature to 4200K
  lumatray --set contrast 50              Set master contrast to 50%
  lumatray --apply-profile "Night"        Apply the 'Night Owl' or custom profile
  lumatray --diagnose                     Run diagnostics and permissions check
  lumatray --circadian                    Show current circadian automation status
  lumatray --toggle-night                 Toggle between daylight and night profiles
        """,
    )

    parser.add_argument("--version", action="version", version=f"LumaTray {__version__}")
    parser.add_argument("--show", action="store_true", help="Open or toggle the quick control panel")
    parser.add_argument("--show-main", action="store_true", help="Open the full 5-tab application suite window")
    parser.add_argument("--list-monitors", action="store_true", help="List connected monitors with identities and states")
    parser.add_argument(
        "--set",
        nargs=2,
        metavar=("FEATURE", "VALUE"),
        help="Set a feature: 'brightness', 'contrast', or 'kelvin' (e.g. --set brightness 75)",
    )
    parser.add_argument(
        "--display",
        type=str,
        default=None,
        help="Target a specific display ID (defaults to all displays)",
    )
    parser.add_argument(
        "--apply-profile",
        type=str,
        metavar="PROFILE_NAME",
        help="Apply a saved scene profile by name or ID (e.g. 'Night', 'Daylight', 'Reading')",
    )
    parser.add_argument("--toggle-night", action="store_true", help="Toggle between Daylight (6500K) and Night (2700K)")
    parser.add_argument("--toggle-auto", action="store_true", help="Toggle circadian auto mode on/off")
    parser.add_argument("--circadian", action="store_true", help="Show current circadian schedule target and override state")
    parser.add_argument("--diagnose", action="store_true", help="Run system diagnostics, check permissions, and latency")
    parser.add_argument("--export-diagnostics", metavar="FILE", help="Export full JSON diagnostic report to file")
    parser.add_argument("--daemon", action="store_true", help="Run LumaTray as background tray daemon (default)")

    return parser


def run_cli(args: Optional[List[str]] = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    # If no action flag given, default to daemon or toggling UI
    has_action = (
        parsed.show
        or parsed.show_main
        or parsed.list_monitors
        or parsed.set
        or parsed.apply_profile
        or parsed.toggle_night
        or parsed.circadian
        or parsed.diagnose
        or parsed.export_diagnostics
    )

    if not has_action and not parsed.daemon:
        # Check if already running; if so, toggle popup
        resp = send_ipc_command({"action": "show"})
        if resp:
            return 0
        parsed.daemon = True

    # 1. Try forwarding to running daemon
    if parsed.show:
        resp = send_ipc_command({"action": "show"})
        if resp:
            return 0

    if parsed.show_main:
        resp = send_ipc_command({"action": "show_main"})
        if resp:
            return 0

    if parsed.list_monitors:
        resp = send_ipc_command({"action": "list_monitors"})
        if resp and resp.get("status") == "ok":
            _print_monitors(resp.get("monitors", []))
            return 0

    if parsed.set:
        feat, val_str = parsed.set
        try:
            val = int(val_str)
        except ValueError:
            print(f"Error: value must be an integer, got '{val_str}'", file=sys.stderr)
            return 1
        resp = send_ipc_command({
            "action": "set",
            "feature": feat.lower(),
            "value": val,
            "display_id": parsed.display,
        })
        if resp and resp.get("status") == "ok":
            print(f"Successfully set {feat} to {val}")
            return 0

    if parsed.apply_profile:
        resp = send_ipc_command({"action": "apply_profile", "profile": parsed.apply_profile})
        if resp and resp.get("status") == "ok":
            print(f"Profile '{parsed.apply_profile}' applied.")
            return 0

    if parsed.toggle_night:
        resp = send_ipc_command({"action": "toggle_night"})
        if resp and resp.get("status") == "ok":
            print(f"Toggled profile: {resp.get('active_profile')}")
            return 0

    if parsed.circadian:
        resp = send_ipc_command({"action": "circadian_status"})
        if resp and resp.get("status") == "ok":
            _print_circadian(resp)
            return 0

    if parsed.diagnose:
        from ..services.diagnostics import diagnostics_service
        report = diagnostics_service.generate_full_report()
        _print_diagnostics(report)
        return 0

    if parsed.export_diagnostics:
        from ..services.diagnostics import diagnostics_service
        out_path = diagnostics_service.export_report_to_file(parsed.export_diagnostics)
        print(f"Diagnostic report exported to: {out_path}")
        return 0

    # If action was requested but daemon wasn't running, run direct fallback
    if parsed.list_monitors:
        from ..services.monitor_service import monitor_service
        from ..services.control_engine import control_engine
        mons = monitor_service.discover_monitors()
        data = []
        for m in mons:
            st = control_engine.get_state(m.id)
            data.append({
                "id": m.id,
                "name": m.name,
                "type": m.display_type.value,
                "connector": m.connector_name,
                "bus": m.bus,
                "brightness": st.brightness,
                "contrast": st.contrast,
                "color_temp": st.color_temp,
            })
        _print_monitors(data)
        return 0

    if parsed.set:
        from ..services.monitor_service import monitor_service
        from ..services.control_engine import control_engine
        feat, val_str = parsed.set
        val = int(val_str)
        mons = monitor_service.discover_monitors()
        if parsed.display:
            if feat == "brightness":
                control_engine.set_brightness(parsed.display, val)
            elif feat == "contrast":
                control_engine.set_contrast(parsed.display, val)
            elif feat in ("kelvin", "color_temp"):
                control_engine.set_color_temp(parsed.display, val)
        else:
            if feat == "brightness":
                control_engine.set_master_brightness(val)
            elif feat == "contrast":
                control_engine.set_master_contrast(val)
            elif feat in ("kelvin", "color_temp"):
                control_engine.set_master_color_temp(val)
        print(f"Set {feat} to {val}")
        return 0

    if parsed.apply_profile:
        from ..services.monitor_service import monitor_service
        from ..services.profile_manager import profile_manager
        monitor_service.discover_monitors()
        if profile_manager.apply_profile(parsed.apply_profile):
            print(f"Applied profile '{parsed.apply_profile}'")
            return 0
        else:
            print(f"Profile '{parsed.apply_profile}' not found", file=sys.stderr)
            return 1

    if parsed.toggle_night:
        from ..services.monitor_service import monitor_service
        from ..services.control_engine import control_engine
        from ..services.profile_manager import profile_manager
        mons = monitor_service.discover_monitors()
        if mons:
            cur_k = control_engine.get_state(mons[0].id).color_temp
            tgt = "daylight" if cur_k < 4500 else "night"
            profile_manager.apply_profile(tgt)
            print(f"Toggled profile to: {tgt}")
            return 0
        return 1

    if parsed.toggle_auto:
        from ..services.automation_engine import automation_engine
        new_state = automation_engine.toggle_auto_mode()
        print(f"Auto Mode: {'Enabled' if new_state else 'Disabled'}")
        return 0

    if parsed.circadian:
        from ..services.automation_engine import automation_engine
        from ..storage.config_store import config_store
        t_br, t_co, t_ct = automation_engine.evaluate_circadian_target()
        _print_circadian({
            "status": "ok",
            "enabled": config_store.get("circadian_enabled", True),
            "target_brightness": t_br,
            "target_contrast": t_co,
            "target_kelvin": t_ct,
            "override_active": automation_engine.is_override_active(),
            "override_remaining_seconds": automation_engine.get_override_remaining_seconds(),
        })
        return 0


    return 0


def _print_monitors(monitors: List[dict]):
    print(f"\n{'ID':<16} {'NAME':<24} {'TYPE':<20} {'BRIGHTNESS':<12} {'CONTRAST':<10} {'KELVIN'}")
    print("=" * 85)
    for m in monitors:
        print(
            f"{m.get('id', ''):<16} "
            f"{m.get('name', ''):<24} "
            f"{m.get('type', ''):<20} "
            f"{m.get('brightness', 0):>3}%         "
            f"{m.get('contrast', 0):>3}%       "
            f"{m.get('color_temp', 6500)}K"
        )
    print()


def _print_circadian(status: dict):
    print("\nLumaTray Circadian & Automation Status:")
    print("-" * 45)
    print(f"  Circadian Enabled: {status.get('enabled')}")
    print(f"  Target Brightness: {status.get('target_brightness')}%")
    print(f"  Target Contrast:   {status.get('target_contrast')}%")
    print(f"  Target Color Temp: {status.get('target_kelvin')}K")
    override = status.get("override_active")
    print(f"  Manual Override:   {'ACTIVE' if override else 'Inactive'}")
    if override:
        rem = status.get("override_remaining_seconds", 0)
        print(f"  Override Resumes:  in {rem // 60}m {rem % 60}s")
    print()


def _print_diagnostics(report: dict):
    print("\nLumaTray System Diagnostics:")
    print("=" * 55)
    perms = report.get("permissions", {})
    print(f"  User:                 {perms.get('user')}")
    print(f"  In 'i2c' group:       {'YES' if perms.get('in_i2c_group') else 'NO (Run: sudo usermod -aG i2c $USER)'}")
    print(f"  In 'video' group:     {'YES' if perms.get('in_video_group') else 'NO'}")
    print("\nInstalled Helper Tools:")
    for tool, info in report.get("tools", {}).items():
        status = "INSTALLED" if info.get("installed") else "MISSING"
        ver = f"({info.get('version')})" if info.get("version") else ""
        print(f"  - {tool:<15} {status:<12} {ver}")
    print("\nLatency Benchmarks:")
    for metric, ms in report.get("latencies", {}).items():
        print(f"  - {metric:<25} {ms} ms")
    print(f"\nConnected Displays Detected: {len(report.get('displays', []))}")
    for d in report.get("displays", []):
        ident = d.get("identity", {})
        print(f"  - [{ident.get('id')}] {ident.get('name')} (bus {ident.get('bus')}, {ident.get('connector_name')})")
    print()
