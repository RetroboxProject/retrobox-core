"""Generator of the Cemu (Wii U) command."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations


from retrobox.configgen.hotkeys import HotkeyAction, Keys
from retrobox.paths import BIOS, configure_emulator, mkdir_if_not_exists

from ... import Command
from ...controller import generate_sdl_game_controller_config
from ..Generator import Generator
from . import cemu_config, cemuControllers
from .cemuPaths import (
    _CEMU_XDG,
    CEMU,
    CEMU_BIOS,
    CEMU_CONFIG,
    CEMU_CONTROLLER_PROFILES,
    CEMU_SAVES,
)




class CemuGenerator(Generator):
    """Generates the Cemu command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def hotkey_bindings(self, system):
        """Ctrl+Tab is Cemu's TV/GamePad view switch."""
        return {HotkeyAction.SWAP_SCREENS: Keys(("KEY_LEFTCTRL", "KEY_TAB"))}

    def hasInternalMangoHUDCall(self) -> bool:
        """Cemu gets neither the MangoHud HUD nor the bezels: they cause game issues."""
        return True

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
        # in case of squashfs, the root directory is passed
        if paths := list(rom.glob("**/code/*.rpx")):
            rom = paths[0]

        mkdir_if_not_exists(CEMU_BIOS)
        mkdir_if_not_exists(CEMU_CONFIG)

        # graphic packs and controller profiles
        mkdir_if_not_exists(CEMU_SAVES / "graphicPacks")
        mkdir_if_not_exists(CEMU_CONTROLLER_PROFILES)

        cemu_config.write_settings(CEMU_CONFIG / "settings.xml", system)

        # Set-up the controllers
        cemuControllers.generateControllerConfig(system, playersControllers)

        if configure_emulator(rom):
            command_array = [CEMU.require()]
        else:
            command_array = [CEMU.require(), "-f", "-g", rom, "--force-no-menubar"]

        return Command.Command(
            array=command_array,
            env={
                "XDG_CONFIG_HOME": f"{_CEMU_XDG}",
                "XDG_DATA_HOME": f"{BIOS}",
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(
                    playersControllers
                ),
                "SDL_JOYSTICK_HIDAPI": "0",
            },
        )
