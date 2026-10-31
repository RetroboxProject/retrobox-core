"""Command line of the setup screen (normally run by the launcher)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import Options, SetupScreen
from .i18n import pick_language


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and show the screen; returns the exit status."""
    parser = argparse.ArgumentParser(
        prog="python3 -m retrobox.emusetup",
        description="Offer to install a missing emulator, full screen.",
    )
    parser.add_argument("--label", required=True, help="emulator name shown to the user")
    parser.add_argument(
        "--log", required=True, type=Path, help="file the installer output is saved to"
    )
    parser.add_argument("--background", type=Path, help="background picture (PNG)")
    parser.add_argument(
        "--check", type=Path, help="file that must exist after a successful install"
    )
    parser.add_argument("--pad-guid", help="SDL GUID of player 1's controller")
    parser.add_argument("--pad-device", help="device path of player 1's controller")
    parser.add_argument(
        "--pad-map", action="append", default=[], metavar="NAME=TYPE:ID:VALUE",
        help="player 1 input from es_input.cfg (repeatable)",
    )
    parser.add_argument("--menu-font", type=Path, help="font of the message and buttons")
    parser.add_argument("--help-font", type=Path, help="font of the hint line")
    parser.add_argument(
        "--lang", help="language of the texts (default: from the system locale)"
    )
    parser.add_argument("--icon", type=Path, help="window icon (PNG)")
    parser.add_argument("--wm-class", help="X11 WM_CLASS / Wayland app_id of the window")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="installer command, after --")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("missing the installer command (after --)")
    return SetupScreen(
        Options(
            label=args.label,
            command=command,
            log_path=args.log,
            background=args.background,
            check_path=args.check,
            pad_guid=args.pad_guid,
            pad_device=args.pad_device,
            pad_mapping=args.pad_map,
            menu_font=args.menu_font,
            help_font=args.help_font,
            language=args.lang or pick_language(),
            icon=args.icon,
            wm_class=args.wm_class,
        )
    ).run()


if __name__ == "__main__":
    sys.exit(main())
