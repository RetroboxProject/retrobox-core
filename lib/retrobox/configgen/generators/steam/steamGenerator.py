"""Generator for Steam games (.steam launchers) and Steam Big Picture."""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import RUNTIME_DIR

from ... import Command
from ..Generator import Generator
from . import steam_monitor

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext

BIGPICTURE_ROM_NAME = "steam.steam"
BIGPICTURE_ROM_CONTENT = "steam"
RUNGAMEID_PREFIX = "steam://rungameid/"

_MONITOR_MODULE = "retrobox.configgen.generators.steam.steam_monitor"


def _find_steam_binary() -> str:
    """The Steam executable, or plain "steam" to let PATH decide."""
    candidates = (
        "/usr/bin/steam",
        "/usr/local/bin/steam",
        str(Path.home() / ".local/bin/steam"),
    )
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "steam"


def _is_bigpicture_rom(rom: Path) -> bool:
    """Whether the rom is "steam.steam" holding just the word "steam".

    Such a rom starts Steam in Big Picture mode instead of a given game.
    """
    if rom.name.lower() != BIGPICTURE_ROM_NAME:
        return False
    try:
        return rom.read_text(encoding="utf-8").strip() == BIGPICTURE_ROM_CONTENT
    except OSError:
        return False


def _read_appid(rom: Path) -> str | None:
    """The AppId of a .steam launcher ("steam://rungameid/<id>")."""
    with rom.open(encoding="utf-8") as launcher:
        first_line = launcher.readline().strip()
    appid = first_line.removeprefix(RUNGAMEID_PREFIX)
    if appid == first_line or not appid.isdigit():
        return None
    return appid


def _remove_legacy_wrappers() -> None:
    """Delete the bash wrappers older versions left in the runtime dir."""
    for old in glob.glob(str(RUNTIME_DIR / "steam_wrapper_*.sh")):
        try:
            os.remove(old)
        except OSError:
            pass


class SteamGenerator(Generator):
    """Runs steam_monitor, which launches the game and waits for its end."""

    def generate(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, system, rom, playersControllers, metadata, guns, wheels, gameResolution
    ):
        """The monitor command for this .steam launcher (or Big Picture)."""
        _remove_legacy_wrappers()
        config = system.config

        command: list[str] = [
            sys.executable, "-m", _MONITOR_MODULE,
            "--steam-bin", _find_steam_binary(),
        ]
        if _is_bigpicture_rom(rom):
            command.append("--big-picture")
        else:
            appid = _read_appid(rom)
            if appid is None:
                raise ValueError(f"{rom} is not a {RUNGAMEID_PREFIX}<AppId> launcher")
            command += [
                "--appid", appid,
                "--exit-grace", str(config.get_int(
                    "steam_exit_grace", steam_monitor.DEFAULT_EXIT_GRACE)),
                "--relaunch-grace", str(config.get_int(
                    "steam_relaunch_grace", steam_monitor.DEFAULT_RELAUNCH_GRACE)),
            ]

        if config.get_bool("close_game_launcher", False):
            command.append("--close-launcher")

        # The launcher waits for the monitor, which waits for the game.
        return Command.Command(array=command, env={})

    def getMouseMode(self, config, rom):
        """Steam games are driven by the mouse too."""
        return True

    def getHotkeysContext(self) -> HotkeysContext:
        """Alt+F4 closes the game."""
        return {
            "name": "steam",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }
