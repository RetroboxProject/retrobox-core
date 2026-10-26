"""Generator of the PPSSPP (PlayStation Portable) command."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

from typing import TYPE_CHECKING

from retrobox.configgen.Emulator import generate_bash_wrapper
from retrobox.paths import SAVES, configure_emulator, ensure_symlink

from ... import Command
from ...controller import Controller, generate_sdl_game_controller_config
from ..Generator import Generator
from . import ppssppConfig, ppssppControllers
from .ppssppPaths import _PPSSPP_CFGDIR, _PPSSPP_PSPDIR, _PPSSPP_XDG, PPSSPP_BIN

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext, Resolution

_LOW_RESOLUTION = 480  # below it, PPSSPP's menu is too big


def _is_low_resolution(resolution: Resolution) -> bool:
    """Tell whether the screen is small enough for the menu to need a lower DPI."""
    return resolution["width"] <= _LOW_RESOLUTION or resolution["height"] <= _LOW_RESOLUTION


class PPSSPPGenerator(Generator):
    """Generates the PPSSPP command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def getHotkeysContext(self) -> HotkeysContext:
        """Return the PPSSPP hotkeys."""
        return {
            "name": "ppsspp",
            "keys": {
                "exit": ["KEY_LEFTALT", "KEY_F4"],
                "menu": "KEY_F9",
                "pause": "KEY_F9",
                "rewind": "KEY_F1",
                "fastforward": "KEY_F2",
                "next_slot": "KEY_F6",
                "previous_slot": "KEY_F5",
                "save_state": "KEY_F3",
                "restore_state": "KEY_F4",
            },
        }

    def usesOpenGLDirectPreload(self, config) -> bool:
        """MangoHud is preloaded when the graphics API that ends up used is OpenGL."""
        return ppssppConfig.uses_opengl(config)

    def allows_bezel(self, config) -> bool:
        """PPSSPP gets the MangoHud HUD and the tattoo, but never a bezel."""
        return False

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
        ensure_symlink(_PPSSPP_PSPDIR, _PPSSPP_CFGDIR / "PSP")

        ppssppConfig.write_ppsspp_config(system)

        # Remove the old gamecontrollerdb.txt file
        (_PPSSPP_CFGDIR / "gamecontrollerdb.txt").unlink(missing_ok=True)

        # Generate the controls.ini
        if controller := Controller.find_player_number(playersControllers, 1):
            ppssppControllers.generateControllerConfig(controller)

        # The command to run
        args_array = []
        if not configure_emulator(rom):
            args_array.extend(["--fullscreen", str(rom)])

        # Adapt the menu size to low definition
        if _is_low_resolution(gameResolution):
            args_array.extend(["--dpi", "0.5"])

        # state_slot option
        if state_filename := system.config.get("state_filename"):
            args_array.append(f"--state={state_filename}")

        command_wrapper = [generate_bash_wrapper(system.config.emulator, PPSSPP_BIN, args_array)]

        return Command.Command(
            array=command_wrapper,
            env={
                "XDG_CONFIG_HOME": _PPSSPP_XDG,
                "XDG_DATA_HOME": SAVES,
                # the hotkey button is used to open the menu
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(
                    playersControllers, ignore_buttons=["hotkey"]
                ),
            },
        )

    def getMouseMode(self, config, rom):
        """Show the mouse on screen, for PPSSPP's own config screen."""
        return True

    def getInGameRatio(self, config, gameResolution, rom):
        """The PSP screen is 16:9."""
        return 16 / 9
