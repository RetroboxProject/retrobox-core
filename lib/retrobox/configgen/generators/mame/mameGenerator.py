"""Generator of the MAME command."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import SAVES, mkdir_if_not_exists

from ... import Command
from ...utils.bezel_policy import NO_BEZEL, configured_bezel, is_bezel_forced_off
from ..Generator import Generator
from . import mame_command, mameControllers
from .mame_bezel import MameBezelRequest, write_bezel_config
from .mame_control_scheme import get_control_scheme
from .mame_game import MameGame, create_game
from .mame_media import game_arguments
from .mamePaths import _MAME_XDG

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext
    from ...config import Config
    from ...Emulator import Emulator
    from .mame_command import CommandLine

_logger = logging.getLogger(__name__)


def _decorations_option(config: Config) -> str | None:
    """Return the "decorations" value mameControllers expects.

    ``NO_BEZEL`` means the user does not want any bezel (the CD-i then uses its
    plain 4:3 view instead of the artwork one), which is also what
    ``force_no_bezel`` asks for. None means no bezel was chosen.
    """
    if is_bezel_forced_off(config):
        return NO_BEZEL
    return config.get_str("bezel") or None


def _write_bezel(game: MameGame, resolution) -> None:
    """Write the artwork of the game, falling back to no bezel if it fails.

    Whether a bezel may be drawn at all is decided by ``bezel_policy``.
    """
    request = MameBezelRequest(
        system=game.system,
        rom=game.rom,
        resolution=resolution,
        bezel=configured_bezel(game.system.config),
        machine_name=game.mess.sys_name if game.mess is not None else "",
    )
    try:
        write_bezel_config(request)
    except Exception:  # pylint: disable=broad-exception-caught
        # best effort: a broken bezel must never prevent the game from starting
        _logger.exception("Error with bezel %s", request.bezel)
        write_bezel_config(replace(request, bezel=None))


def _build_command_line(
    game: MameGame, resolution
) -> tuple[CommandLine, Path, mame_command.InputOptions]:
    """Build the MAME command line, in the order MAME documents its options.

    Returns:
        The command line, the folder of the game config and the input options.
    """
    system = game.system
    cmd = mame_command.base_options(game)

    cfg_path = mame_command.config_directory(game)
    cmd += mame_command.directory_options(game, cfg_path)
    cmd += mame_command.video_options(system, resolution)
    cmd += mame_command.plugin_options(system)

    input_options = mame_command.input_options(game)
    cmd += input_options.arguments
    cmd += mame_command.screen_options(system)

    # finally we pass the game name
    cmd += game_arguments(game)
    return [mame_command.MAME_BIN, *cmd], cfg_path, input_options


def _custom_command(rom: Path) -> list[str] | None:
    """Return the command the user gave in a ``<rom>.cmd`` file, if there is one."""
    custom_file = Path(f"{rom}.cmd")
    if custom_file.is_file():
        return custom_file.read_text(encoding="utf-8").splitlines()
    return None


class MameGenerator(Generator):
    """Generates the MAME command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def supportsInternalBezels(self) -> bool:
        """MAME draws its own artwork, so MangoHud must not draw a bezel."""
        return True

    def getHotkeysContext(self) -> HotkeysContext:
        """Return the MAME hotkeys."""
        return {
            "name": "mame",
            "keys": {
                "exit": "KEY_ESC",
                "menu": "KEY_TAB",
                "pause": "KEY_F5",
                "reset": "KEY_F3",
                "coin": "KEY_5",
                "fastforward": "KEY_PAGEDOWN",
                "save_state": ["KEY_LEFTSHIFT", "KEY_F6"],
                "restore_state": ["KEY_LEFTSHIFT", "KEY_F7"],
            },
        }

    # the signature is fixed by the Generator interface
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def generate(
        self,
        system: Emulator,
        rom,
        playersControllers,  # name fixed by the Generator interface
        metadata,
        guns,
        wheels,
        gameResolution,  # name fixed by the Generator interface
    ):
        for directory in mame_command.userdata_directories():
            mkdir_if_not_exists(directory)

        game = create_game(system, rom)
        command_array, cfg_path, input_options = _build_command_line(game, gameResolution)

        _write_bezel(game, gameResolution)

        mameControllers.generatePadsConfig(
            cfg_path,
            playersControllers,
            game.model if game.mess is not None else "",
            get_control_scheme(system, rom),
            system.config.get_bool("customcfg"),
            game.special_controller,
            _decorations_option(system.config),
            system.config.use_guns,
            guns,
            system.config.use_wheels,
            wheels,
            input_options.use_mouse,
            input_options.multi_mouse,
            system,
        )

        # if the user provided a custom cmd file at the default location, use it
        custom_command = _custom_command(rom)
        if custom_command is not None:
            command_array = custom_command

        # change directory to the MAME folder (allows the data plugin to load properly)
        os.chdir(mame_command.working_directory())
        return Command.Command(
            array=command_array,
            env={
                "PWD": f"{mame_command.working_directory()}/",
                "XDG_CONFIG_HOME": _MAME_XDG,
                "XDG_CACHE_HOME": SAVES,
            },
        )
