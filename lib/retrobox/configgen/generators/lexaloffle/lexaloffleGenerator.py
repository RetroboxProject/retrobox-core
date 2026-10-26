from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final

from retrobox.configgen.generators.lexaloffle.lexaloffle_paths import PICO8_BIN_PATH, PICO8_CONTROLLERS, PICO8_ROOT_PATH, VOX_BIN_PATH, VOX_CONTROLLERS, VOX_ROOT_PATH
from retrobox.paths import (
    BIOS,
    SCREENSHOTS,
    ensure_parents_and_open
)

from ... import Command

from ...controller import generate_sdl_game_controller_config
from ...exceptions import RetroboxException
from ..Generator import Generator

if TYPE_CHECKING:
    from pathlib import Path

    from ...typedefs import HotkeysContext



# Generator for the official pico8 binary from Lexaloffle
class LexaloffleGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "lexaloffle",
            "keys": { "exit": ["KEY_LEFTCTRL", "KEY_Q"], "menu": "KEY_ENTER", "reset": [ "KEY_LEFTCTRL", "KEY_R" ] }
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        if system.name == "pico8":
            LD_LIB = PICO8_ROOT_PATH
            BIN_PATH = PICO8_BIN_PATH
            CONTROLLERS = PICO8_CONTROLLERS
            ROOT_PATH = PICO8_ROOT_PATH
        elif system.name == "voxatron":
            LD_LIB = VOX_BIN_PATH
            BIN_PATH = VOX_BIN_PATH
            CONTROLLERS = VOX_CONTROLLERS
            ROOT_PATH = VOX_ROOT_PATH
        else:
            raise RetroboxException(
                f"The Lexaloffle generator has been called for an unknwon system: {system.name}.")

        if not BIN_PATH.exists():
            raise RetroboxException(
                f"Lexaloffle official binary not found at {BIN_PATH}")

        if not os.access(BIN_PATH, os.X_OK):
            raise RetroboxException(
                f"{BIN_PATH} is not set as executable")

        # the command to run
        command_array: list[str | Path] = [BIN_PATH]
        command_array.extend(["-desktop", SCREENSHOTS])  # screenshots
        command_array.extend(["-windowed", "0"])                     # full screen
        # Display FPS
        if system.config.display_fps:
            command_array.extend(["-display_fps", "1"])
        else:
            command_array.extend(["-display_fps", "0"])

        rombase = rom.stem

        # .m3u support for multi-cart pico-8
        if rom.suffix.lower() == ".m3u":
            with rom.open() as fpin:
                lines = fpin.readlines()
            fullpath = rom.absolute().parent / lines[0].strip()
            command_array.extend(["-root_path", fullpath.parent])
            rom = fullpath
        else:
            command_array.extend(["-root_path", ROOT_PATH]) # store carts from splore

        if (rombase.lower() == "splore" or rombase.lower() == "console"):
            command_array.extend(["-splore"])
        else:
            command_array.extend(["-run", rom])

        controllersconfig = generate_sdl_game_controller_config(playersControllers)
        with ensure_parents_and_open(CONTROLLERS, "w") as file:
            file.write(controllersconfig)

        existing_library_path = os.environ.get("LD_LIBRARY_PATH")

        return Command.Command(array=command_array, env={
            "SDL_AUDIODRIVER": "alsa",
            "LD_LIBRARY_PATH":
                f"{LD_LIB}:{existing_library_path}" if existing_library_path else LD_LIB
        })

    def getInGameRatio(self, config, gameResolution, rom):
        return 4/3
