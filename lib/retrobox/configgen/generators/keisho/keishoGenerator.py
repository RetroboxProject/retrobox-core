"""Generator of the Keisho (Sega Model 2) command.

Keisho is a native Model 2 emulator (https://github.com/Keisho-Emu/Keisho),
installed with ``retrobox --setup-emulator keisho``.
"""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

from typing import TYPE_CHECKING

from retrobox.paths import configure_emulator, mkdir_if_not_exists

from ... import Command
from ...controller import generate_sdl_game_controller_config
from ...exceptions import RetroboxException
from ..Generator import Generator
from . import keisho_config
from .keisho_games import game_set
from .keisho_paths import (
    KEISHO_BIN,
    KEISHO_CFGDIR,
    KEISHO_NVRAM,
    KEISHO_SCREENSHOTS,
    migrate_legacy_data,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ...config import SystemConfig


class KeishoGenerator(Generator):
    """Generates the Keisho command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def usesOpenGLDirectPreload(self, config) -> bool:
        """MangoHud is preloaded unless the picture is drawn with Vulkan."""
        return keisho_config.uses_opengl(config)

    def allows_bezel(self, config: SystemConfig) -> bool:
        """A picture that is not 4:3 (16:9, square pixels, stretched) has no bezel."""
        return keisho_config.bezel_fits(config)

    def getInGameRatio(self, config, gameResolution, rom):
        """Return the aspect ratio of the picture Keisho shows."""
        return keisho_config.get_in_game_ratio(config, gameResolution)

    # the signature is fixed by the Generator interface
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def generate(
        self,
        system,
        rom,
        playersControllers,  # name fixed by the Generator interface
        metadata,
        guns,
        wheels,
        gameResolution,  # name fixed by the Generator interface
    ):
        if not KEISHO_BIN.exists():
            raise RetroboxException(
                f"keisho not found in {KEISHO_BIN}: run 'retrobox --setup-emulator keisho'"
            )

        migrate_legacy_data()
        for directory in (KEISHO_CFGDIR, KEISHO_NVRAM, KEISHO_SCREENSHOTS):
            mkdir_if_not_exists(directory)

        # the configuration GUI is Keisho's own game picker, with its overlay (F10)
        game = None if configure_emulator(rom) else rom
        keisho_config.write_config(system, game, playersControllers, wheels, gameResolution)

        command: list[str | Path] = [KEISHO_BIN, "--config", KEISHO_CFGDIR]
        if game is not None:
            # A merged archive holds every revision of a game and Keisho would
            # boot the first complete one it knows: the archive name picks it.
            if (named_set := game_set(game)) is not None:
                command.extend(["--game", named_set])
            command.append(game)

        return Command.Command(
            array=command,
            env={
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(
                    playersControllers
                ),
                # with HIDAPI off SDL reports the /dev/input/eventN nodes pad1/2_device name
                "SDL_JOYSTICK_HIDAPI": "0",
            },
        )
