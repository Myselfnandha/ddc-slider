"""
LumaTray main executable entry point.
"""

from __future__ import annotations

import logging
import sys

from .application import LumaTrayApplication
from .integrations.cli import run_cli

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> int:
    # If explicit CLI command flags are provided
    cli_flags = {
        "--help", "-h", "--version", "--list-monitors", "--set",
        "--apply-profile", "--toggle-night", "--circadian",
        "--diagnose", "--export-diagnostics",
    }
    args = sys.argv[1:]

    # Check if this invocation is purely a CLI command
    if any(arg in cli_flags for arg in args):
        return run_cli(args)

    if "--show-main" in args:
        from .integrations.dbus_service import send_ipc_command
        if send_ipc_command({"action": "show_main"}):
            return 0
        app = LumaTrayApplication()
        return app.run(start_hidden=False)

    if "--show" in args:
        from .integrations.dbus_service import send_ipc_command
        if send_ipc_command({"action": "show"}):
            return 0
        app = LumaTrayApplication()
        return app.run(start_hidden=True)

    # Start application daemon
    app = LumaTrayApplication()
    return app.run(start_hidden=True)


if __name__ == "__main__":
    sys.exit(main())
