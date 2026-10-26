"""Generator of the PCSX2 (PlayStation 2) command."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import configure_emulator, mkdir_if_not_exists

from ... import Command
from ...controller import generate_sdl_game_controller_config, write_sdl_controller_db
from ...Emulator import generate_bash_wrapper
from ...exceptions import RetroboxException
from ..Generator import Generator
from . import pcsx2_config
from .pcsx2_controllers import (
    get_wheel_type,
    is_playing_with_wheel,
    use_emulator_wheels,
    wheelTypeMapping,
)
from .pcsx2_paths import PCSX2_BIN, PCSX2_DBFILE, _PCSX2_CFGDIR, PCSX2_PATCHES, _PCSX2_XDG

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext
    from ...config import SystemConfig

_logger = logging.getLogger(__name__)

_OBSOLETE_CONFIG_FILES = ("PCSX2_ui.ini", "PCSX2_vm.ini", "GS.ini")


def _check_cpu() -> None:
    """Make sure the CPU has the SSE4.1 PCSX2 requires.

    Raises:
        RetroboxException: If the CPU does not support SSE4.1.
    """
    with Path("/proc/cpuinfo").open(encoding="utf8") as cpuinfo:
        if not re.search(r"^flags\s*:.*\ssse4_1\W", cpuinfo.read(), re.MULTILINE):
            raise RetroboxException("CPU does not support SSE4.1, which is required by pcsx2.")


def _remove_obsolete_configs() -> None:
    """Remove the config files of older versions of PCSX2."""
    for filename in _OBSOLETE_CONFIG_FILES:
        (_PCSX2_CFGDIR / "inis" / filename).unlink(missing_ok=True)


class Pcsx2Generator(Generator):
    """Generates the PCSX2 command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def getHotkeysContext(self) -> HotkeysContext:
        """Return the PCSX2 hotkeys."""
        return {
            "name": "pcsx2",
            "keys": {
                "exit": ["KEY_LEFTALT", "KEY_F4"],
                "menu": "KEY_ESC",
                "save_state": "KEY_F1",
                "restore_state": "KEY_F3",
                "previous_slot": ["KEY_LEFTSHIFT", "KEY_F2"],
                "next_slot": "KEY_F2",
            },
        }

    def usesOpenGLDirectPreload(self, config) -> bool:
        """MangoHud is preloaded when the renderer that ends up used is OpenGL."""
        return pcsx2_config.uses_opengl(config)

    def allows_bezel(self, config: SystemConfig) -> bool:
        """A picture that is not 4:3 (16:9, stretched) leaves no room for a bezel."""
        return pcsx2_config.bezel_fits(config)

    def getInGameRatio(self, config, gameResolution, rom):
        """Return the aspect ratio of the picture PCSX2 shows."""
        return pcsx2_config.get_in_game_ratio(config, gameResolution)

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
        _check_cpu()
        _remove_obsolete_configs()

        playing_with_wheel = is_playing_with_wheel(system, wheels)
        pcsx2_config.configure_ini(
            system, playersControllers, metadata, guns, wheels, playing_with_wheel
        )

        # write our own game_controller_db.txt file before launching the game
        write_sdl_controller_db(playersControllers, PCSX2_DBFILE)

        args = []
        if not configure_emulator(rom):
            args = ["-nogui", "-batch", "-fullscreen", str(rom)]

        env: dict[str, str | Path] = {"XDG_CONFIG_HOME": _PCSX2_XDG}

        # wheels won't work correctly when SDL_GAMECONTROLLERCONFIG is set, and
        # excluding the wheels from it does not fix that either
        wheel_type = get_wheel_type(metadata, playing_with_wheel, system.config, wheelTypeMapping)
        if not use_emulator_wheels(playing_with_wheel, wheel_type):
            env["SDL_GAMECONTROLLERCONFIG"] = generate_sdl_game_controller_config(
                playersControllers
            )

        # ensure we have the patches.zip file to avoid message.
        mkdir_if_not_exists(PCSX2_PATCHES.parent)
        if not PCSX2_PATCHES.exists():
            _logger.debug("patches.zip not found in %s, skipping", PCSX2_PATCHES)

        if state_filename := system.config.get("state_filename"):
            args.extend(["-statefile", state_filename])
        if state_slot := system.config.get_str("state_slot"):
            args.extend(["-stateindex", state_slot])

        command_wrapper = [generate_bash_wrapper(system.config.emulator, PCSX2_BIN, args)]
        return Command.Command(array=command_wrapper, env=env)
