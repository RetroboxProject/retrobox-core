"""The launch sequence: from a ROM to the exit code of its emulator."""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.configgen import profiler
from retrobox.configgen.controller import Controller
from retrobox.configgen.Emulator import Emulator
from retrobox.configgen.generators import get_generator
from retrobox.configgen.gun import Gun
from retrobox.configgen.utils import metadata, videoMode, wheelsUtils
from retrobox.configgen.utils.overlayfs import mount_overlayfs
from retrobox.configgen.utils.squashfs import mount_squashfs
from retrobox.paths import (
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
    ES_GAMES_METADATA,
    ES_INPUT_CFG,
    RUNTIME_DIR,
    SAVES,
    mkdir_if_not_exists,
)

from .controller_monitor import ControllerMonitor
from .gun_overlays import draw_internal_gun_borders, generate_gun_help
from .hooks import call_game_hooks
from .hud import setup_hud
from .power import apply_power_profile, restore_power_profile
from .process import run_command
from .session import GameInputs, GameSession, effective_core

if TYPE_CHECKING:
    import argparse
    from contextlib import AbstractContextManager

    from retrobox.configgen.generators.Generator import Generator

_logger = logging.getLogger(__name__)

_GAME_INFO_FILE = Path("/tmp/game.xml")


def run_rom(args: argparse.Namespace, max_players: int) -> int:
    """Run a ROM, mounting it first if it is squashed.

    Args:
        args: Parsed command-line arguments.
        max_players: Maximum number of players/controllers supported.

    Returns:
        The exit code of the launched emulator command.
    """
    original_rom = args.rom

    # squashfs roms if squashed
    if original_rom.suffix == ".squashfs":
        with mount_squashfs(original_rom) as squash_rom:
            return start_rom(args, max_players, squash_rom, original_rom)
    return start_rom(args, max_players, original_rom, original_rom)


def _log_system_settings(system: Emulator) -> None:
    """Log the system settings (hiding passwords) and the selected emulator/core."""
    _logger.debug(
        "Settings: %s",
        {key: "***" if "password" in key else value for key, value in system.config.items()},
    )

    if "emulator" in system.config and "core" in system.config:
        _logger.debug("emulator: %s, core: %s", system.config.emulator, system.config.core)
    elif "emulator" in system.config:
        _logger.debug("emulator: %s", system.config.emulator)


def _game_rom_context(
    system: Emulator, generator: Generator, rom: Path, original_rom: Path
) -> AbstractContextManager[Path]:
    """Return the context that provides the ROM the emulator will actually use.

    A squashed ROM the emulator writes to is mounted on top of an overlay
    filesystem that keeps the writes in the saves directory.
    """
    if original_rom.suffix == ".squashfs" and generator.writesToRom(system.config):
        return mount_overlayfs(rom, Path(f"{SAVES}/{original_rom.parent.name}/{original_rom.stem}"))
    return contextlib.nullcontext(rom)


def start_rom(args: argparse.Namespace, max_players: int, rom: Path, original_rom: Path) -> int:
    """Run the main ROM start sequence, calling into the rest of the package.

    Args:
        args: Parsed command-line arguments.
        max_players: Maximum number of players/controllers supported.
        rom: The (possibly squashfs-mounted) rom path to launch.
        original_rom: The original, unmounted rom path.

    Returns:
        The exit code of the launched emulator command.
    """
    mkdir_if_not_exists(RUNTIME_DIR)

    player_controllers = Controller.load_for_players(max_players, args)
    monitor = ControllerMonitor(player_controllers)

    # find the system to run
    _logger.debug("Running system: %s", args.system)
    system = Emulator(args, original_rom)
    _log_system_settings(system)

    # power profiles
    previous_power_profile = apply_power_profile(system.config.get("power_profile", "balanced"))

    game_metadata = metadata.get_games_meta_data(ES_GAMES_METADATA, args.system, rom)
    guns = Gun.get_and_precalibrate_all(system, rom)

    exit_code = 0
    with wheelsUtils.configure_wheels(
        player_controllers, system, game_metadata
    ) as (controllers, wheels):
        # find the generator
        generator = get_generator(system.config.emulator, system.config.core)

        with _game_rom_context(system, generator, rom, original_rom) as game_rom:
            exit_code = _run_game(
                GameSession(
                    args=args,
                    system=system,
                    generator=generator,
                    rom=game_rom,
                    resolution=videoMode.getCurrentResolution(),
                    metadata=game_metadata,
                    inputs=GameInputs(
                        controllers=controllers, guns=guns, wheels=wheels, monitor=monitor
                    ),
                ),
                previous_power_profile,
            )
    return exit_code


def _prepare_game_environment(system: Emulator) -> None:
    """Create the save directory and set the SDL VSync environment."""
    Path(f"{SAVES}/{system.name}").mkdir(parents=True, exist_ok=True)

    # SDL VSync is a big deal on OGA and RPi4
    system.config["sdlvsync"] = "1" if system.config.get_bool("sdlvsync", True) else "0"
    os.environ.update({"SDL_RENDER_VSYNC": system.config["sdlvsync"]})


def _run_game(session: GameSession, previous_power_profile: str | None) -> int:
    """Run hooks and the emulator for a game, restoring the power profile at the end."""
    try:
        _prepare_game_environment(session.system)

        # run a script before emulator starts
        call_game_hooks(session, "on-start-game")

        exit_code = _run_emulator(session)

        # run a script after emulator shuts down
        call_game_hooks(session, "on-close-game")
        return exit_code
    finally:
        restore_power_profile(previous_power_profile)
        _GAME_INFO_FILE.unlink(missing_ok=True)


def _gamepad_manager(**kwargs):
    """Gamepadly (pad -> keyboard hotkeys) is a separate package; run without it if absent."""
    try:
        from gamepadly import GamepadManager
    except ImportError:
        _logger.warning("gamepadly is not installed: gamepad hotkeys (e.g. Hotkey+Start) are disabled")
        return contextlib.nullcontext()
    return GamepadManager(**kwargs)


def _run_emulator(session: GameSession) -> int:
    """Generate the emulator command, set up HUD and gun helpers, and run it."""
    system = session.system

    with _gamepad_manager(
        system=session.args.system,
        emulator=system.config.emulator,
        core=effective_core(system),
        rom=session.rom,
        controllers=session.inputs.controllers,
        profiles_dir=_GAMEPADLY_PROFILES,
        user_profiles_dir=_GAMEPADLY_USER_PROFILES,
        es_input=ES_INPUT_CFG,
    ):
        # change directory if wanted
        execution_directory = session.generator.executionDirectory(system.config, session.rom)
        if execution_directory is not None:
            os.chdir(execution_directory)

        cmd = session.generator.generate(
            system,
            session.rom,
            session.inputs.controllers,
            session.metadata,
            session.inputs.guns,
            session.inputs.wheels,
            session.resolution,
        )

        setup_hud(session, cmd)
        generate_gun_help(session)
        draw_internal_gun_borders(session)

        with profiler.pause():
            session.inputs.monitor.start()
            return run_command(cmd)
