"""Generator of the Supermodel (Sega Model 3) command."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import EMULATORS, LOGS

from ... import Command
from ...controller import generate_sdl_game_controller_config
from ...gun import guns_need_crosses
from ..Generator import Generator
from .supermodel_config import configPadsIni
from .supermodel_paths import _SUPERMODEL_EMUDIR, SUPERMODEL_BIN

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext
    from ...config import SystemConfig

_WIDESCREEN_OPTION = "m3_wideScreen"


def _crosshairs_option(system, guns) -> list[str]:
    """Return the crosshairs option: the user's one, or one if the guns need it."""
    if crosshairs := system.config.get("crosshairs"):
        return [f"-crosshairs={crosshairs}"]
    if guns_need_crosses(guns):
        return ["-crosshairs=1" if len(guns) == 1 else "-crosshairs=3"]
    return []


def _graphics_options(config: SystemConfig) -> list[str]:
    """Return the options that depend on the graphics settings."""
    options: list[str] = []
    if config.get("engine3D") == "new3d":
        options.append("-new3d")
    else:
        options.extend(["-multi-texture", "-legacy-scsp", "-legacy3d"])

    if config.get_bool(_WIDESCREEN_OPTION):
        options.extend(["-wide-screen", "-wide-bg"])

    if config.get_bool("quadRendering"):
        options.append("-quad-rendering")
    return options


def _tuning_options(config: SystemConfig) -> list[str]:
    """Return the options the user tunes: force feedback, frequency, colors, upscaling."""
    options: list[str] = []
    if config.get_bool("forceFeedback"):
        options.append("-force-feedback")
    if freq := config.get("ppcFreq"):
        options.append(f"-ppc-frequency={freq}")
    if color := config.get("crt_colour"):
        options.append(f"-crtcolors={color}")
    if upscale_mode := config.get("upscale_mode"):
        options.append(f"-upscalemode={upscale_mode}")
    return options


class SupermodelGenerator(Generator):
    """Generates the Supermodel command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def getHotkeysContext(self) -> HotkeysContext:
        """Return the Supermodel hotkeys."""
        return {
            "name": "supermodel",
            "keys": {
                "exit": "KEY_ESC",
                "menu": ["KEY_LEFTALT", "KEY_P"],
                "pause": ["KEY_LEFTALT", "KEY_P"],
                "reset": ["KEY_LEFTALT", "KEY_R"],
                "save_state": "KEY_F5",
                "restore_state": "KEY_F7",
                "next_state": "KEY_F6",
            },
        }

    def allows_bezel(self, config: SystemConfig) -> bool:
        """A widescreen picture leaves no room for a bezel."""
        return not config.get_bool(_WIDESCREEN_OPTION)

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
        command_array: list[str | Path] = [SUPERMODEL_BIN, "-fullscreen", "-channels=2"]
        command_array.extend(_graphics_options(system.config))
        command_array.extend(_crosshairs_option(system, guns))
        command_array.extend(_tuning_options(system.config))
        command_array.append(f"-res={gameResolution['width']},{gameResolution['height']}")
        command_array.extend([f"-log-output={LOGS}/Supermodel.log", rom])

        # controller config
        configPadsIni(system, rom, guns)
        os.chdir(_SUPERMODEL_EMUDIR)
        return Command.Command(
            array=command_array,
            env={
                "XDG_CONFIG_HOME": EMULATORS,
                "SDL_VIDEODRIVER": "x11",
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
                "SDL_JOYSTICK_HIDAPI": "0",
            },
        )

    def getInGameRatio(self, config, gameResolution, rom):
        """Return the ratio of the game image: 16/9 in widescreen mode."""
        if config.get("m3_wideScreen") == "1":
            return 16 / 9
        return 4 / 3
