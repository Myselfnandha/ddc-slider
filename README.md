# LumaTray — Next-Generation GTK3 Monitor Control Suite

**LumaTray** is a modular monitor-control platform for Linux (optimized for Arch Linux, XFCE/X11, with Wayland readiness), featuring hardware DDC/CI control, sysfs backlight management, color temperature coordination, smart circadian automation, multi-monitor scene profiles, hotkeys, system diagnostics, and scripting integration.

---

## 🚀 Key Highlights & Architecture

LumaTray evolves beyond simple tray sliders into a robust, decoupled display control platform:

- **Core Application Shell**: Multi-backend System Tray (`AppIndicator3` / `Gtk.StatusIcon`), Quick Floating Control Panel, Translucent OSD, and a 5-destination Suite Window.
- **Hardware & Desktop Adapters**:
  - `ddcutil_backend`: Serialized per-bus queues, coalesced writes, `_last_written_val` caching to eliminate duplicate I2C traffic.
  - `backlight_sysfs`: Direct kernel sysfs backlight access for internal laptop screens with `brightnessctl` and `xrandr` fallbacks.
  - `color_x11`: Tanner-Helland 1000K–10000K Kelvin converter with X11 GPU gamma ramp mapping.
  - `color_wayland`: Wayland compositor color management (Gammastep, KDE Plasma KWin Night Color D-Bus, GNOME Night Light).
  - `colord_backend`: Gentle external color management conflict detection without process kill wars.
  - `ambient_light`: Linux Industrial I/O (IIO) ambient illuminance reader with logarithmic perceptual response curve.
- **Smart Automation Engine**: Continuous multi-waypoint circadian day/night curves (smooth cosine interpolation), ambient adaptation, idle dimming, and manual override tracking with auto-resume.
- **Profiles & Scenes**: Pre-seeded system profiles (Daylight, Reading, Coding, Movie, Gaming, Night Owl, Candlelight), custom profiles, pre-apply snapshot backups with visual diff previews, and JSON import/export.
- **Display Protection & VCP Safety**: Destructive factory-reset VCP commands (`0x04`, `0x05`, `0x08`) are strictly blocked. Input source switching (`0x60`) requires explicit confirmation.

---

## 🖥 5 UI Destinations

1. **Overview**: Live master controls, per-monitor slider cards, quick preset scenes, and automation status chips.
2. **Displays**: Hardware capability inspector, MCCS version reporting, discrete VCP color presets (`0x14`), hardware RGB gains (`0x16`, `0x18`, `0x1A`), safe input switching (`0x60`), raw diagnostic VCP reader, and one-click display snapshot backup.
3. **Profiles**: Scene cards, preview differences before applying, duplicate/delete/create, and JSON import/export.
4. **Automation**: Circadian waypoints schedule table, ambient light adaptation toggle, idle dimming power saving, and configurable manual override pause timeout.
5. **Settings & Diagnostics**: System permissions inspector (`/dev/i2c-*` nodes and user group membership), helper tool verification, hardware latency benchmarks, hotkey reference, and one-click diagnostic report JSON export.

---

## ⌨ Command-Line Interface (CLI) & Scripting

LumaTray provides a fast UNIX-socket IPC and standalone CLI:

```bash
# Toggle quick brightness popup
lumatray --show

# Open the full 5-tab Monitor Control Suite window
lumatray --show-main

# List all detected displays with identities, types, and current values
lumatray --list-monitors

# Adjust master values across all displays
lumatray --set brightness 75
lumatray --set contrast 50
lumatray --set kelvin 4200

# Target a specific monitor by ID
lumatray --display internal_intel_backlight --set brightness 80

# Apply a saved scene profile
lumatray --apply-profile "Reading"
lumatray --apply-profile "Night"

# Toggle between Daylight (6500K) and Night (2700K)
lumatray --toggle-night

# Inspect circadian curve status and manual override countdown
lumatray --circadian

# Run hardware permissions and latency diagnostics
lumatray --diagnose

# Export diagnostics snapshot
lumatray --export-diagnostics /tmp/report.json
```

---

## 📦 Directory Structure

```
lumatray/
├── bin/
│   └── lumatray                     # Main executable wrapper
├── src/
│   └── lumatray/
│       ├── __init__.py
│       ├── __main__.py              # Entry point dispatcher
│       ├── application.py           # Application lifecycle coordinator
│       ├── core/                    # Models, errors, events, capabilities, validation
│       │   ├── models.py
│       │   ├── errors.py
│       │   ├── events.py
│       │   ├── validation.py
│       │   └── capability_registry.py
│       ├── backends/                # Hardware & desktop adapters
│       │   ├── ddcutil_backend.py
│       │   ├── backlight_sysfs.py
│       │   ├── color_x11.py
│       │   ├── color_wayland.py
│       │   ├── colord_backend.py
│       │   └── ambient_light.py
│       ├── services/                # Business logic services
│       │   ├── monitor_service.py
│       │   ├── control_engine.py
│       │   ├── color_service.py
│       │   ├── profile_manager.py
│       │   ├── automation_engine.py
│       │   ├── osd_manager.py
│       │   └── diagnostics.py
│       ├── ui/                      # GTK3 interfaces & styles
│       │   ├── styles.py
│       │   ├── tray.py
│       │   ├── quick_panel.py
│       │   ├── osd.py
│       │   ├── overview_view.py
│       │   ├── displays_view.py
│       │   ├── profiles_view.py
│       │   ├── automation_view.py
│       │   ├── settings_view.py
│       │   └── main_window.py
│       ├── integrations/            # Desktop integrations
│       │   ├── dbus_service.py
│       │   ├── cli.py
│       │   ├── hotkeys.py
│       │   └── desktop_events.py
│       └── storage/                 # Persistence & configuration
│           ├── config_store.py
│           ├── profile_store.py
│           └── migrations.py
├── data/
│   └── lumatray.desktop
├── packaging/
│   ├── PKGBUILD
│   ├── systemd/lumatray.service
│   └── udev/99-i2c-ddc.rules
├── tests/
│   ├── test_validation.py
│   ├── test_models.py
│   ├── test_events.py
│   ├── test_circadian.py
│   ├── test_color.py
│   └── run_tests.py
└── pyproject.toml
```

---

## 🛠 Running Tests

Execute the test suite:

```bash
python3 tests/run_tests.py
```

---

## 📄 License

MIT License. Designed and crafted for Linux monitor control.
