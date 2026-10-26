"""Command-line interface of the emulator launcher."""

from __future__ import annotations

import argparse
from pathlib import Path

MAX_PLAYERS = 8

# per-player command-line options: (suffix, help text, type)
_PLAYER_ARGUMENTS = (
    ("index", "controller index", int),
    ("guid", "controller SDL2 guid", str),
    ("name", "controller name", str),
    ("devicepath", "controller device", str),
    ("nbbuttons", "controller number of buttons", int),
    ("nbhats", "controller number of hats", int),
    ("nbaxes", "controller number of axes", int),
)
# plain string command-line options: (name, help text)
_STRING_ARGUMENTS = (
    ("-emulator", "force emulator"),
    ("-core", "force emulator core"),
    ("-netplaymode", "host/client"),
    ("-netplaypass", "enable spectator mode"),
    ("-netplayip", "remote ip"),
    ("-netplayport", "remote port"),
    ("-netplaysession", "netplay session"),
    ("-state_slot", "state slot"),
    ("-state_filename", "state filename"),
    ("-autosave", "autosave"),
    ("-systemname", "system fancy name"),
)
# boolean command-line flags: (name, help text)
_FLAG_ARGUMENTS = (
    ("-lightgun", "configure lightguns"),
    ("-wheel", "configure wheel"),
    ("-trackball", "configure trackball"),
    ("-spinner", "configure spinner"),
)


def _resolve_rom_path(path_str: str) -> Path:
    """Resolve the rom path, leaving the special "config" value untouched."""
    if path_str == "config":
        return Path(path_str)
    return Path(path_str).resolve()


def build_argument_parser(max_players: int = MAX_PLAYERS) -> argparse.ArgumentParser:
    """Build the command-line parser of the launcher.

    Args:
        max_players: How many players get their own ``-p<N>...`` options.

    Returns:
        The configured argument parser.
    """
    parser = argparse.ArgumentParser(description="emulator-launcher script")

    for player in range(1, max_players + 1):
        for suffix, description, arg_type in _PLAYER_ARGUMENTS:
            parser.add_argument(
                f"-p{player}{suffix}",
                help=f"player{player} {description}",
                type=arg_type,
                required=False,
            )

    parser.add_argument("-system", help="select the system to launch", type=str, required=True)
    parser.add_argument("-rom", help="rom absolute path", type=_resolve_rom_path, required=True)

    for name, description in _STRING_ARGUMENTS:
        parser.add_argument(name, help=description, type=str, required=False)

    parser.add_argument(
        "-gameinfoxml",
        help="game info xml",
        type=str,
        nargs="?",
        default="/dev/null",
        required=False,
    )

    for name, description in _FLAG_ARGUMENTS:
        parser.add_argument(name, help=description, action="store_true")

    return parser
