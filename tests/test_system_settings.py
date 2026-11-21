"""retrobox-system: the time zone and keyboard of console mode, through fake systemd tools."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "lib"

_EVDEV = """! model
  pc105           Generic 105-key PC
! layout
  us              English (US)
  es              Spanish
  fr              French
! variant
  dvorak          us: English (Dvorak)
  cat             es: Catalan (Spain, with middle-dot L)
  winkeys         es: Spanish (Windows)
! option
  grp             Switching to another layout
"""

# a tool that logs its arguments, prints $<NAME>_OUT and exits with $<NAME>_STATUS
_FAKE = """#!/bin/sh
echo "$0 $*" >> "$FAKE_LOG"
name=$(basename "$0" | tr a-z A-Z)
eval "out=\\${${name}_OUT:-}"; eval "status=\\${${name}_STATUS:-0}"
[ -n "$out" ] && printf '%s\\n' "$out"
[ "$status" = 0 ] || echo "Interactive authentication required." >&2
exit "$status"
"""


@pytest.fixture(name="system")
def _system(tmp_path: Path) -> dict[str, str]:
    """A system with fake timedatectl and localectl, a zoneinfo and an XKB list."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("timedatectl", "localectl"):
        path = bin_dir / tool
        path.write_text(_FAKE, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "zoneinfo" / "Europe").mkdir(parents=True)
    (tmp_path / "zoneinfo" / "Europe" / "Madrid").write_bytes(b"TZif")
    (tmp_path / "evdev.lst").write_text(_EVDEV, encoding="utf-8")
    keyboard = tmp_path / "keyboard"
    keyboard.write_text('XKBMODEL="pc105"\nXKBLAYOUT="us"\nXKBVARIANT=""\n'
                        'XKBOPTIONS="grp:alt_shift_toggle"\n', encoding="utf-8")
    return {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin",
        "PYTHONPATH": str(_LIB),
        "FAKE_LOG": str(tmp_path / "calls.log"),
        "RETROBOX_ZONEINFO": str(tmp_path / "zoneinfo"),
        "RETROBOX_XKB_RULES": str(tmp_path / "evdev.lst"),
        "RETROBOX_KEYBOARD_FILE": str(keyboard),
        "RETROBOX_LOCALTIME": str(tmp_path / "localtime"),
    }


def _run(env: dict[str, str], *args: str) -> tuple[int, list[str]]:
    result = subprocess.run([sys.executable, "-m", "retrobox.system_settings", *args],
                            env=env, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout.splitlines()


def _calls(env: dict[str, str]) -> list[str]:
    try:
        lines = Path(env["FAKE_LOG"]).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    calls = (line.partition(" ") for line in lines)
    return [f"{Path(tool).name} {args}" for tool, _, args in calls]


def test_timezone(system: dict[str, str]) -> None:
    """get asks timedatectl; set checks the zone exists and sets it without asking a password."""
    assert _run(system | {"TIMEDATECTL_OUT": "Europe/Madrid"}, "timezone", "get") \
        == (0, ["Europe/Madrid"])
    assert _run(system, "timezone", "set", "Europe/Madrid") == (0, [])
    assert "timedatectl --no-ask-password set-timezone Europe/Madrid" in _calls(system)
    for wrong in ("Europe/Nowhere", "../etc/passwd", "Europe/Madrid; rm"):
        status, out = _run(system, "timezone", "set", wrong)
        assert status == 1 and out[-1].startswith("Error: unknown time zone")


def test_timezone_without_systemd(system: dict[str, str], tmp_path: Path) -> None:
    """No timedatectl answer: /etc/localtime's link tells the zone."""
    os.symlink("/usr/share/zoneinfo/Europe/Madrid", tmp_path / "localtime")
    assert _run(system | {"TIMEDATECTL_STATUS": "1"}, "timezone", "get") == (0, ["Europe/Madrid"])


def test_keyboard_lists(system: dict[str, str]) -> None:
    """Layouts by description; a layout's variants without their prefix."""
    assert _run(system, "keyboard", "list-layouts") == (
        0, ["us English (US)", "fr French", "es Spanish"])
    assert _run(system, "keyboard", "list-variants", "es") == (
        0, ["cat Catalan (Spain, with middle-dot L)", "winkeys Spanish (Windows)"])
    assert _run(system, "keyboard", "get") == (0, ["us none"])


def test_keyboard_set(system: dict[str, str]) -> None:
    """set keeps the model and options, and refuses what XKB doesn't know."""
    assert _run(system, "keyboard", "set", "es", "winkeys") == (0, [])
    assert _run(system, "keyboard", "set", "fr", "none") == (0, [])
    assert _calls(system) == [
        "localectl --no-ask-password set-x11-keymap es pc105 winkeys grp:alt_shift_toggle",
        "localectl --no-ask-password set-x11-keymap fr pc105  grp:alt_shift_toggle",
    ]
    assert _run(system, "keyboard", "set", "xx")[1][-1] == "Error: unknown keyboard layout 'xx'"
    assert _run(system, "keyboard", "set", "es", "dvorak")[1][-1].startswith(
        "Error: the keyboard layout 'es' has no variant")


def test_refused_without_permission(system: dict[str, str]) -> None:
    """When polkit says no, the error says why, as EmulationStation shows it."""
    status, out = _run(system | {"LOCALECTL_STATUS": "1"}, "keyboard", "set", "es")
    assert status == 1
    assert out[-1].startswith("Error: cannot change the keyboard layout: "
                              "Interactive authentication required.")
    assert "polkit rule" in out[-1]
