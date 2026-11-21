"""The system's time zone and keyboard layout, for EmulationStation's console mode.

In console mode (``[core] console_mode``) EmulationStation is the only screen,
so its system settings offer the time zone and the keyboard layout, as
batocera's do (retrobox-emulationstation's patch 0019); this is what they run,
as ``retrobox-system``, in place of ``batocera-timezone`` and
``batocera-keyboard``.

Both are the system's own settings, not Retrobox's: they are set through
systemd (``timedatectl``, ``localectl``, which keep them where the
distribution does: /etc/localtime, /etc/default/keyboard on Debian...), so
everything else on the machine sees the same, and read back from there.
Without a password: Retrobox's polkit rule (50-retrobox-console-settings.rules)
lets an administrator at the console do these two things. The layouts and
variants are XKB's (``/usr/share/X11/xkb/rules/evdev.lst``). A new keyboard
layout applies the next time the session starts (retrobox-labwc reads the
system's keyboard then); a new time zone, at once.

Output is for EmulationStation: lists are ``<code> <description>`` lines, and
a failure ends with an ``Error: ...`` line (and exit status 1).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

ZONEINFO: Final = Path(os.environ.get("RETROBOX_ZONEINFO", "/usr/share/zoneinfo"))
XKB_RULES: Final = Path(os.environ.get("RETROBOX_XKB_RULES", "/usr/share/X11/xkb/rules/evdev.lst"))
KEYBOARD_FILE: Final = Path(os.environ.get("RETROBOX_KEYBOARD_FILE", "/etc/default/keyboard"))
LOCALTIME: Final = Path(os.environ.get("RETROBOX_LOCALTIME", "/etc/localtime"))

_TIMEZONE = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+)*$")
_XKB_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_NO_VARIANT: Final = "none"
_TIMEOUT: Final = 30


class SettingError(Exception):
    """A setting could not be read or changed; the message says why, for a person."""


## Time zone ------------------------------------------------------------------------


def current_timezone() -> str:
    """The system's time zone (``Europe/Madrid``), or ``""`` if it can't be told."""
    value = _run_quiet(["timedatectl", "show", "--property=Timezone", "--value"])
    if value:
        return value
    try:  # no systemd running: /etc/localtime points into the zoneinfo folder
        target = os.readlink(LOCALTIME)
    except OSError:
        return ""
    parts = Path(target).parts
    return "/".join(parts[parts.index("zoneinfo") + 1:]) if "zoneinfo" in parts else ""


def set_timezone(zone: str) -> None:
    """Set the system's time zone.

    Raises:
        SettingError: Not a known time zone, or the system didn't accept it.
    """
    if not _TIMEZONE.match(zone) or ".." in zone or not (ZONEINFO / zone).is_file():
        raise SettingError(f"unknown time zone '{zone}'")
    _change(["timedatectl", "--no-ask-password", "set-timezone", zone], "the time zone")


## Keyboard -------------------------------------------------------------------------


def _xkb_section(name: str) -> list[tuple[str, str]]:
    """The ``(code, description)`` lines of one ``! <name>`` section of the XKB rules list."""
    try:
        lines = XKB_RULES.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        raise SettingError(f"no keyboard layouts on this system ({XKB_RULES}: {error})") from error
    entries, inside = [], False
    for line in lines:
        if line.startswith("!"):
            inside = line[1:].strip() == name
        elif inside and line.strip():
            code, _, description = line.strip().partition(" ")
            entries.append((code, description.strip()))
    return entries


def layouts() -> list[tuple[str, str]]:
    """Every keyboard layout: ``(code, description)``, by description."""
    return sorted(_xkb_section("layout"), key=lambda entry: entry[1].casefold())


def variants(layout: str) -> list[tuple[str, str]]:
    """The variants of a layout: ``(code, description)``, without the ``<layout>:`` prefix."""
    prefix = f"{layout}:"
    return [(code, description.removeprefix(prefix).strip())
            for code, description in _xkb_section("variant") if description.startswith(prefix)]


def _keyboard_file() -> dict[str, str]:
    values = {}
    try:
        for line in KEYBOARD_FILE.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*(XKB\w+)=[\"']?([^\"'#]*?)[\"']?\s*(#.*)?$", line)
            if match:
                values[match[1]] = match[2]
    except OSError:
        pass
    return values


def current_keyboard() -> dict[str, str]:
    """The system's keyboard: ``layout``, ``variant``, ``model`` and ``options`` (``""`` unset).

    From /etc/default/keyboard (Debian's keyboard-configuration), else localectl,
    the same places retrobox-labwc's session reads it from.
    """
    file = _keyboard_file()
    if file.get("XKBLAYOUT"):
        return {"layout": file["XKBLAYOUT"], "variant": file.get("XKBVARIANT", ""),
                "model": file.get("XKBMODEL", ""), "options": file.get("XKBOPTIONS", "")}
    status = _run_quiet(["localectl", "status"])
    fields = {}
    for line in status.splitlines():
        key, _, value = line.strip().partition(":")
        if key.startswith("X11 "):
            fields[key[4:].strip().lower()] = "" if value.strip() == "n/a" else value.strip()
    return {"layout": fields.get("layout", ""), "variant": fields.get("variant", ""),
            "model": fields.get("model", ""), "options": fields.get("options", "")}


def set_keyboard(layout: str, variant: str = "") -> None:
    """Set the system's keyboard layout (and variant), keeping its model and options.

    Raises:
        SettingError: Not a known layout or variant, or the system didn't accept it.
    """
    variant = "" if variant == _NO_VARIANT else variant
    if not _XKB_CODE.match(layout) or layout not in dict(layouts()):
        raise SettingError(f"unknown keyboard layout '{layout}'")
    if variant and (not _XKB_CODE.match(variant) or variant not in dict(variants(layout))):
        raise SettingError(f"the keyboard layout '{layout}' has no variant '{variant}'")
    current = current_keyboard()
    _change(["localectl", "--no-ask-password", "set-x11-keymap", layout,
             current["model"], variant, current["options"]], "the keyboard layout")


## Running the system's tools -------------------------------------------------------------


def _run_quiet(command: list[str]) -> str:
    """The output of a command, or ``""`` if it isn't there or fails."""
    if shutil.which(command[0]) is None:
        return ""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False,
                                timeout=_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _change(command: list[str], what: str) -> None:
    if shutil.which(command[0]) is None:
        raise SettingError(
            f"cannot change {what}: {command[0]} is not installed (it needs systemd)")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False,
                                timeout=_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        raise SettingError(f"cannot change {what}: {error}") from error
    if result.returncode != 0:
        reason = (result.stderr or result.stdout).strip().splitlines()
        detail = reason[-1] if reason else f"{command[0]} exited with {result.returncode}"
        if "authoriz" in detail.lower() or "interactive authentication" in detail.lower():
            detail += " (only an administrator at the console may: see Retrobox's polkit rule)"
        raise SettingError(f"cannot change {what}: {detail}")


## Command line -----------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retrobox-system",
        description="The system's time zone and keyboard layout (EmulationStation's console mode).")
    topics = parser.add_subparsers(dest="topic", required=True)
    timezone = topics.add_parser("timezone", help="the time zone").add_subparsers(
        dest="action", required=True)
    timezone.add_parser("get", help="print the time zone")
    timezone.add_parser("set", help="set the time zone").add_argument("zone")
    keyboard = topics.add_parser("keyboard", help="the keyboard layout").add_subparsers(
        dest="action", required=True)
    keyboard.add_parser("get", help="print '<layout> <variant>' (variant: none)")
    keyboard.add_parser("list-layouts", help="print '<code> <description>' lines")
    keyboard.add_parser("list-variants", help="the same, for one layout").add_argument("layout")
    change = keyboard.add_parser("set", help="set the layout (and variant)")
    change.add_argument("layout")
    change.add_argument("variant", nargs="?", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``retrobox-system``; returns the exit status."""
    args = _parser().parse_args(argv)
    try:
        match (args.topic, args.action):
            case ("timezone", "get"):
                print(current_timezone())
            case ("timezone", "set"):
                set_timezone(args.zone)
            case ("keyboard", "get"):
                keyboard = current_keyboard()
                print(f"{keyboard['layout'] or 'us'} {keyboard['variant'] or _NO_VARIANT}")
            case ("keyboard", "list-layouts"):
                for code, description in layouts():
                    print(f"{code} {description}")
            case ("keyboard", "list-variants"):
                for code, description in variants(args.layout):
                    print(f"{code} {description}")
            case ("keyboard", "set"):
                set_keyboard(args.layout, args.variant)
    except SettingError as error:
        print(f"Error: {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
