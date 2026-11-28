"""Generator for Linux apps: executable ``.sh`` and ``.run`` files that run as they are."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from retrobox.configgen import Command
from retrobox.configgen.controller import generate_sdl_game_controller_config
from retrobox.configgen.exceptions import RetroboxException
from retrobox.configgen.generators.Generator import Generator

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from retrobox.configgen.config import SystemConfig
    from retrobox.configgen.controller import Controllers
    from retrobox.configgen.Emulator import Emulator
    from retrobox.configgen.gun import Guns
    from retrobox.configgen.typedefs import DeviceInfoMapping, Resolution


def _has_shebang(script: Path) -> bool:
    """Whether the file starts with ``#!``, which the kernel needs to run a script."""
    try:
        with script.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


class LinuxappGenerator(Generator):
    """Run an app of the *Linux apps* system: the file itself, which must be executable."""

    def generate(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        system: Emulator,
        rom: Path,
        playersControllers: Controllers,
        metadata: Mapping[str, str],
        guns: Guns,
        wheels: DeviceInfoMapping,
        gameResolution: Resolution,
    ) -> Command.Command:
        """Return the command that runs the app; fail clearly if it cannot be run."""
        if not rom.is_file():
            raise RetroboxException(f"Linux app not found: {rom}")
        if not os.access(rom, os.X_OK):
            raise RetroboxException(
                f"Linux app is not executable: {rom} (run: chmod +x '{rom.name}')"
            )

        # a .sh without a shebang cannot be exec'd by the kernel: hand it to bash
        if rom.suffix.lower() == ".sh" and not _has_shebang(rom):
            command = ["/bin/bash", str(rom)]
        else:
            command = [str(rom)]

        return Command.Command(
            array=command,
            env={
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(
                    playersControllers
                ),
            },
        )

    def executionDirectory(self, config: SystemConfig, rom: Path) -> Path | None:
        """Run the app from its own folder, as when it is started from a file manager."""
        return rom.parent

    def hasInternalMangoHUDCall(self) -> bool:
        """An arbitrary app gets neither the HUD nor a bezel."""
        return True

    def hotkeys_opt_in(self) -> bool:
        """Pad hotkeys (Hotkey+Start...) are only mapped if the overlay is turned on."""
        return True
