"""Generator of the sm2-emu (Sega Model 2) command.

sm2-emu is a native Model 2 emulator (https://github.com/dmanlfc/sm2-emu),
installed with ``retrobox --setup-emulator sm2-emu``.
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
from . import sm2emu_config
from .sm2emu_games import game_set
from .sm2emu_paths import (
    SM2EMU_BIN,
    SM2EMU_CFGDIR,
    SM2EMU_NVRAM,
    SM2EMU_SCREENSHOTS,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ...config import SystemConfig
    from ...typedefs import HotkeysContext


class Sm2EmuGenerator(Generator):
    """Generates the sm2-emu command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def getHotkeysContext(self) -> HotkeysContext:
        """Return the sm2-emu hotkeys (its default keys, which the generator enforces)."""
        return {
            "name": "sm2-emu",
            "keys": {
                "exit": "KEY_F9",
                "menu": "KEY_F10",
                "pause": "KEY_P",
                "screenshot": "KEY_F12",
                "save_state": "KEY_F6",
                "restore_state": "KEY_F7",
                "rewind": "KEY_BACKSPACE",
                "fastforward": "KEY_TAB",
                "coin": "KEY_5",
            },
        }

    def usesOpenGLDirectPreload(self, config) -> bool:
        """MangoHud is preloaded unless the picture is drawn with Vulkan."""
        return sm2emu_config.uses_opengl(config)

    def allows_bezel(self, config: SystemConfig) -> bool:
        """A picture that is not 4:3 (16:9, square pixels, stretched) has no bezel."""
        return sm2emu_config.bezel_fits(config)

    def getInGameRatio(self, config, gameResolution, rom):
        """Return the aspect ratio of the picture sm2-emu shows."""
        return sm2emu_config.get_in_game_ratio(config, gameResolution)

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
        if not SM2EMU_BIN.exists():
            raise RetroboxException(
                f"sm2-emu not found in {SM2EMU_BIN}: run 'retrobox --setup-emulator sm2-emu'"
            )

        for directory in (SM2EMU_CFGDIR, SM2EMU_NVRAM, SM2EMU_SCREENSHOTS):
            mkdir_if_not_exists(directory)

        # the configuration GUI is sm2-emu's own game picker, with its overlay (F10)
        game = None if configure_emulator(rom) else rom
        sm2emu_config.write_config(system, game, playersControllers, wheels, gameResolution)

        command: list[str | Path] = [SM2EMU_BIN, "--config", SM2EMU_CFGDIR]
        if game is not None:
            # A merged archive holds every revision of a game and sm2-emu would
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
