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
from retrobox.configgen.gun import Guns
from retrobox.configgen.hotkeys import binding_to_json
from retrobox.configgen.utils import metadata, videoMode, wheelsUtils
from retrobox.configgen.utils.overlayfs import mount_overlayfs
from retrobox.configgen.utils.squashfs import mount_squashfs
from retrobox.paths import (
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
    ES_GAME_INFO,
    ES_GAMES_METADATA,
    ES_INPUT_CFG,
    ES_MENU_THEME,
    RUNTIME_DIR,
    SAVES,
    SESSION_PAD_PROFILE,
    mkdir_if_not_exists,
)

from .controller_monitor import ControllerMonitor
from .emulator_setup import ensure_emulator
from .game_state import GameState, clear_state, process_start_time, write_state
from .hooks import call_game_hooks
from .hud import setup_hud
from .pad_profile import build_session_profile, effective_bindings
from .power import apply_power_profile, restore_power_profile
from .process import run_command
from .session import GameInputs, GameSession, effective_core
from .hotkey_held import hotkey_held

if TYPE_CHECKING:
    import argparse
    import subprocess
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from retrobox.configgen.generators.Generator import Generator

_logger = logging.getLogger(__name__)



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
    # read right away, while the button that launched the game is likely still
    # down: the hotkey held asks for the emulator to be installed again
    args.reinstall_emulator = hotkey_held(player_controllers)
    monitor = ControllerMonitor(player_controllers)

    # find the system to run
    _logger.debug("Running system: %s", args.system)
    system = Emulator(args, original_rom)
    _log_system_settings(system)

    # find the generator
    generator = get_generator(system.config.emulator, system.config.core)

    # a missing emulator: offer to install it, or go back to the frontend;
    # hotkey held: offer to install it again (to update it)
    if not ensure_emulator(
        system.config.emulator,
        player_controllers,
        reinstall=getattr(args, "reinstall_emulator", False),
    ):
        return 0

    # power profiles
    previous_power_profile = apply_power_profile(system.config.get("power_profile", "balanced"))

    game_metadata = metadata.get_games_meta_data(ES_GAMES_METADATA, args.system, rom)
    guns: Guns = []  # light guns are unsupported

    exit_code = 0
    with wheelsUtils.configure_wheels(
        player_controllers, system, game_metadata
    ) as (controllers, wheels):
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
        clear_state()
        SESSION_PAD_PROFILE.unlink(missing_ok=True)
        restore_power_profile(previous_power_profile)
        ES_GAME_INFO.unlink(missing_ok=True)


def _gamepad_manager(session: GameSession) -> AbstractContextManager[object]:
    """Run gamepadly with the game's profile plus the standard hotkeys.

    Gamepadly (pad -> keyboard mappings and hotkeys) is a separate package:
    the game runs without it when it is absent.
    """
    try:
        # pylint: disable-next=import-outside-toplevel
        from gamepadly import GamepadManager, find_profile
    except ImportError:
        _logger.warning(
            "gamepadly is not installed: gamepad hotkeys (e.g. Hotkey+Start) are disabled"
        )
        return contextlib.nullcontext()

    system = session.system
    lookup = {
        "rom": session.rom,
        "system": session.args.system,
        "emulator": system.config.emulator,
        "core": effective_core(system),
        "profiles_dir": _GAMEPADLY_PROFILES,
        "user_profiles_dir": _GAMEPADLY_USER_PROFILES,
    }
    profile = build_session_profile(
        session.generator, system, find_profile(**lookup), SESSION_PAD_PROFILE
    )
    manager_args = {
        **lookup,
        "controllers": session.inputs.controllers,
        "es_input": ES_INPUT_CFG,
    }
    try:
        return GamepadManager(**manager_args, profile=profile)
    except TypeError:
        _logger.warning("gamepadly is older than 0.1.4: the standard hotkeys are disabled")
        return GamepadManager(**manager_args)


def _controllers_json(session: GameSession) -> list[dict[str, object]]:
    """The game's controllers as session.json lists them (the overlay grabs their devices)."""
    return [
        {
            "player": controller.player_number,
            "guid": controller.guid,
            "name": controller.real_name,
            "device": controller.physical_device_path or controller.device_path,
        }
        for controller in session.inputs.controllers
    ]


def _publish_state(session: GameSession) -> Callable[[subprocess.Popen[bytes]], None]:
    """Return the callback that writes session.json once the emulator has started.

    Called after ``generate()``: the generator knows by then how its game is
    started, so it can tell how to end it.
    """
    system = session.system
    generator = session.generator
    exit_env = {
        name: list(values)
        for name, values in generator.exit_env(system, session.rom).items()
    }
    hotkeys = {
        action.value: binding_to_json(binding)
        for action, binding in effective_bindings(generator, system).items()
    }

    def on_started(process: subprocess.Popen[bytes]) -> None:
        write_state(
            GameState(
                pid=process.pid,
                pgid=process.pid,  # start_new_session: the emulator leads its group
                start_time=process_start_time(process.pid) or 0,
                launcher_pid=os.getpid(),
                system=session.args.system,
                emulator=system.config.emulator,
                core=effective_core(system),
                rom=str(session.rom),
                metadata=dict(session.metadata),
                exit_timeout=generator.exit_timeout(system.config),
                exit_env=exit_env,
                controllers=_controllers_json(session),
                hotkeys=hotkeys,
                game_info=str(ES_GAME_INFO),
                menu_theme=str(ES_MENU_THEME),
            )
        )

    return on_started


def _run_emulator(session: GameSession) -> int:
    """Generate the emulator command, set up HUD and gun helpers, and run it."""
    system = session.system

    with _gamepad_manager(session):
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

        with profiler.pause():
            session.inputs.monitor.start()
            return run_command(cmd, on_started=_publish_state(session))
