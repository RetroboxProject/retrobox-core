"""Generator of the DuckStation command."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

from os import environ
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import ensure_parents_and_open

from ... import Command
from ...controller import generate_sdl_game_controller_config, write_sdl_controller_db
from ...utils.configparser import CaseSensitiveConfigParser
from ..Generator import Generator
from . import duckstation_settings as sections
from .duckstation_files import rewrite_m3u_full_path
from .duckstation_generator import _DUCKSTATION_XDG, DUCKSTATION_CFG
from .duckstation_pads import configure_pads

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext
    from ...config import SystemConfig

_QT_BINARY = Path("/usr/bin/duckstation-qt")
_SDL_CONTROLLER_DB = "/usr/share/duckstation/resources/gamecontrollerdb.txt"


def _command_array(rom: Path) -> list[str | Path]:
    """Return the DuckStation command: the Qt build if installed, else the nogui one."""
    if _QT_BINARY.exists():
        return ["duckstation-qt", "-batch", "-nogui", "--", rom]
    return ["duckstation-nogui", "-batch", "-fullscreen", "--", rom]


def _write_settings(config: SystemConfig, controllers, guns, metadata) -> None:
    """Update DuckStation's settings.ini from the configuration of the game."""
    settings = CaseSensitiveConfigParser(interpolation=None)
    if DUCKSTATION_CFG.exists():
        settings.read(DUCKSTATION_CFG)

    sections.configure_main(settings, config)
    sections.configure_controller_ports(settings)
    sections.configure_console(settings, config)
    sections.configure_bios(settings, config)
    sections.configure_cpu(settings, config)
    sections.configure_gpu(settings, config)
    sections.configure_display(settings, config)
    sections.configure_audio(settings, config)
    sections.configure_game_list(settings)
    sections.configure_cheevos(settings, config)
    sections.configure_texture_replacements(settings, config)
    sections.configure_input_sources(settings)
    sections.configure_folders(settings)
    configure_pads(settings, config, controllers, guns, metadata)
    sections.configure_hotkeys(settings)
    sections.configure_cdrom_and_ui(settings, config)

    with ensure_parents_and_open(DUCKSTATION_CFG, "w") as config_file:
        settings.write(config_file)


class DuckstationGenerator(Generator):
    """Generates the DuckStation command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def getHotkeysContext(self) -> HotkeysContext:
        """Return the DuckStation hotkeys."""
        return {
            "name": "duckstation",
            "keys": {
                "exit": ["KEY_LEFTALT", "KEY_F4"],
                "menu": "KEY_F7",
                "reset": "KEY_F6",
                "restore_state": "KEY_F1",
                "save_state": "KEY_F2",
                "previous_slot": "KEY_F3",
                "next_slot": "KEY_F4",
                "rewind": "KEY_F5",
                "fastforward": "KEY_TAB",
                "next_disk": "KEY_F8",
            },
        }

    def allows_bezel(self, config: SystemConfig) -> bool:
        """A ratio other than 4:3, or a stretched picture, leaves no room for a bezel."""
        return sections.bezel_fits_display(config)

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
        # a m3u file needs its discs to have full paths
        if rom.suffix == ".m3u":
            rom = rewrite_m3u_full_path(rom)

        command_array = _command_array(rom)
        _write_settings(system.config, playersControllers, guns, metadata)

        # write our own gamecontrollerdb.txt file before launching the game
        write_sdl_controller_db(playersControllers, _SDL_CONTROLLER_DB)

        qt_qpa_platform = "wayland" if environ.get("WAYLAND_DISPLAY") else "xcb"
        return Command.Command(
            array=command_array,
            env={
                "XDG_CONFIG_HOME": _DUCKSTATION_XDG,
                "QT_QPA_PLATFORM": qt_qpa_platform,
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(
                    playersControllers
                ),
                "SDL_JOYSTICK_HIDAPI": "0",
            },
        )
