"""Generator of the Dolphin (GameCube and Wii) command."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from retrobox.configgen.Emulator import generate_bash_wrapper
from retrobox.paths import configure_emulator, mkdir_if_not_exists

from ... import Command
from ..Generator import Generator
from . import dolphin_config, dolphin_controllers
from .dolphin_paths import (
    _DOLPHIN_CFGDIR,
    _DOLPHIN_XDG,
    DOLPHIN,
    DOLPHIN_NOGUI,
    DOLPHIN_SAVES,
    DOLPHIN_SYSCONF,
)

if TYPE_CHECKING:
    from ...config import SystemConfig

_logger = logging.getLogger(__name__)


class DolphinGenerator(Generator):
    """Generates the Dolphin command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def hotkey_bindings(self, system):
        """Dolphin's own keyboard hotkeys (Hotkeys.ini)."""
        return dolphin_config.hotkey_bindings()

    def usesOpenGLDirectPreload(self, config) -> bool:
        """MangoHud is preloaded when the graphics API that ends up used is OpenGL."""
        return dolphin_config.resolve_gfx_backend(config) == dolphin_config.BACKEND_OPENGL

    def allows_bezel(self, config: SystemConfig) -> bool:
        """A picture that is not 4:3 (16:9, stretched) leaves no room for a bezel."""
        return dolphin_config.bezel_fits(config)

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
        dolphin = DOLPHIN.require()

        # Dirs required for saves
        mkdir_if_not_exists(DOLPHIN_SAVES / "StateSaves")
        mkdir_if_not_exists(DOLPHIN_SAVES / "GameSettings")
        mkdir_if_not_exists(_DOLPHIN_CFGDIR)

        # Controller mapping (per-pad ini files: GCPadNew.ini / WiimoteNew.ini)
        dolphin_controllers.generateControllerConfig(
            system, playersControllers, metadata, wheels, rom, guns
        )

        # Dolphin.ini: custom paths, discord rpc, graphics API, audio gain, controller port types
        dolphin_config.write_dolphin_ini(system, playersControllers, wheels)

        # GFX.ini: aspect ratio, scaling multiplier, GPU adapter for Vulkan
        dolphin_config.write_gfx_ini(system)

        # Hotkeys.ini
        dolphin_config.write_hotkeys_ini()

        # RetroAchievements.ini: EmulationStation's RetroAchievements menu
        dolphin_config.write_achievements_ini(system.config)

        # SYSCONF: keep the Wii's internal aspect-ratio flag in sync
        dolphin_config.update_sysconf_aspect_ratio(system.config, DOLPHIN_SYSCONF)

        dolphin_exec_env = {
            "XDG_CONFIG_HOME": _DOLPHIN_XDG,
            "XDG_DATA_HOME": _DOLPHIN_XDG,
            "LOCPATH": str(DOLPHIN.prefix_of(dolphin) / "share" / "locale"),
            # no HIDAPI: the button numbers of es_input.cfg are evdev's (see startup/run.py)
            "SDL_JOYSTICK_HIDAPI": "0",
            "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1",
        }

        selected_bin = dolphin
        if configure_emulator(rom):
            dolphin_args = []  # config mode, no -b -e
        else:
            dolphin_args = ["-C", "Dolphin.Display.Fullscreen=True", "-e", str(rom)]
            nogui = DOLPHIN_NOGUI.find()
            if nogui is not None:
                selected_bin = nogui
            else:
                # no NoGUI frontend (an AppImage): the GUI one in batch mode
                dolphin_args.insert(0, "-b")

        if state_filename := system.config.get("state_filename"):
            dolphin_args.extend(["--save_state", state_filename])

        command_wrapper = [
            generate_bash_wrapper(system.config.emulator, selected_bin, dolphin_args)
        ]
        return Command.Command(array=command_wrapper, env=dolphin_exec_env)

    def getInGameRatio(self, config, gameResolution, rom):
        """Return the aspect ratio of the picture Dolphin shows."""
        return dolphin_config.get_in_game_ratio(config, gameResolution)
