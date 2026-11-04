"""Generator for Heroic Games Launcher games (Epic, GOG, Amazon, sideloaded).

A Heroic "rom" holds the launch link the PC games sync writes:
``heroic://launch?appName=<id>&runner=<runner>``.
"""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from retrobox.configgen.utils.pc_launchers import launcher_environment

from ... import Command
from ...exceptions import RetroboxException
from ..Generator import Generator


EXIT_TIMEOUT = 10.0
"""Seconds a Heroic game (often Wine) has to quit after SIGTERM."""


def _read_link(rom: Path) -> str:
    """The launch link stored in the rom file."""
    try:
        return rom.read_text(encoding="utf-8").strip()
    except OSError as err:
        raise RetroboxException(f"Cannot read the Heroic launch link {rom}: {err}") from err


def app_name_of(link: str) -> str | None:
    """The game id (Heroic's ``appName``) of a launch link, or None.

    Accepts ``heroic://launch?appName=<id>&runner=<runner>`` and the older
    ``heroic://launch/<runner>/<id>``.
    """
    parts = urlsplit(link)
    if parts.scheme != "heroic" or parts.netloc != "launch":
        return None
    names = parse_qs(parts.query).get("appName")
    if names and names[0]:
        return names[0]
    segments = [segment for segment in parts.path.split("/") if segment]
    return segments[-1] if segments else None


class HeroicGenerator(Generator):
    """Hands the launch link to Heroic, which starts the game."""

    # the signature is fixed by the Generator interface
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        """Run ``heroic --no-gui <link>``."""
        command = ["heroic", "--no-gui", _read_link(rom)]
        return Command.Command(
            array=command, env=launcher_environment(system, playersControllers)
        )

    def getMouseMode(self, config, rom):
        """The mouse is only grabbed when the user asks for it."""
        return config.get_bool("force_mouse")

    def exit_env(self, system, rom):
        """Heroic (2.9.2 and later) puts the game id in the environment of the game."""
        app_name = app_name_of(_read_link(rom))
        return {"HEROIC_APP_NAME": [app_name]} if app_name else {}

    def exit_timeout(self, config):
        """Wine games take a while to close."""
        return EXIT_TIMEOUT
