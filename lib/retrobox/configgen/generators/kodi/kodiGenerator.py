"""Kodi: configgen writes its controllers; bin/retrobox-kodi starts it."""

# The method and argument names are the interface every generator implements.
# pylint: disable=invalid-name,unused-argument,too-many-arguments,too-many-positional-arguments

from __future__ import annotations

from pathlib import Path

from retrobox.configgen.exceptions import RetroboxException

from ... import Command
from ..Generator import Generator
from . import kodiConfig


class KodiGenerator(Generator):
    """Kodi: writes its controller configuration; bin/retrobox-kodi only starts it."""

    # Main entry of the module
    # Configure kodi inputs and return the command to run
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        # EmulationStation's Kodi menu entry has no game: it passes "-rom config"
        if rom != Path("config"):
            with rom.open() as f:
                lines = f.read().splitlines()
            if lines:
                first_line = lines[0].strip()
                if first_line != "kodi":
                    raise RetroboxException('Invalid launcher for kodi')

        # raises when there is no Kodi; Flatpak is preferred over a native one
        kodiConfig.write_kodi_config(playersControllers)
        return Command.Command(array=[kodiConfig.KODI_LAUNCHER])
