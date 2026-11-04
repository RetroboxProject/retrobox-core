from __future__ import annotations

import os
from pathlib import Path

from retrobox.configgen.exceptions import RetroboxException

from ... import Command
from ..Generator import Generator
from . import kodiConfig


def _find_kodi_binary() -> str:
    candidates = [
        "/usr/bin/kodi",
        "/usr/local/bin/kodi",
        str(Path.home() / ".local/bin/kodi"),
        "kodi",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "kodi"

class KodiGenerator(Generator):

    # Main entry of the module
    # Configure kodi inputs and return the command to run
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        with rom.open() as f:
            lines = f.read().splitlines()
        if lines:
            first_line = lines[0].strip()
            if first_line != "kodi":
                raise RetroboxException(f'Invalid launcher for kodi')

        kodiConfig.writeKodiConfig(playersControllers)
        commandArray = [f"{_find_kodi_binary()}"]
        return Command.Command(array=commandArray)
