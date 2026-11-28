"""The launch sequence: from a ROM to the exit code of its emulator."""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.bios import require as require_bios
from retrobox.configgen import profiler
from retrobox.configgen.controller import Controller
from retrobox.configgen.Emulator import Emulator
from retrobox.configgen.generators import get_generator
from retrobox.configgen.gun import Guns
from retrobox.configgen.hotkeys import osk_enabled, overlay_enabled
from retrobox.configgen.utils import achievements, metadata, videoMode, wheelsUtils
from retrobox.configgen.utils.overlayfs import mount_overlayfs
from retrobox.configgen.utils.squashfs import mount_squashfs
from retrobox.paths import (
    ES_GAME_INFO,
    ES_GAMES_METADATA,
    ES_MENU_THEME,
    RUNTIME_DIR,
    SAVES,
    SESSION_PAD_PROFILE,
    configure_emulator,
    mkdir_if_not_exists,
)
from retrobox.utils.overlay_task import reinstall_requested

from . import control as control_channel
from .controller_monitor import ControllerMonitor
from .emulator_setup import ensure_emulator
from .game_state import GameState, clear_state, process_start_time, write_state
from .launch_phase import Phase, set_phase
from .hooks import call_game_hooks
from .hud import setup_hud
from .idle_inhibit import inhibit_idle
from .pad_profile import build_session_profile, effective_bindings, find_profile
from .power import apply_power_profile, restore_power_profile
from .process import run_command
from .session import GameInputs, GameSession, effective_core

if TYPE_CHECKING:
    import argparse
    import subprocess
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from retrobox.configgen.generators.Generator import Generator
    from retrobox.configgen.Command import Command

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
    # down: the chord (L1+R1, Ctrl+Shift) held asks for the emulator to be installed again
    args.reinstall_emulator = reinstall_requested()
    monitor = ControllerMonitor(player_controllers)

    # find the system to run
    _logger.debug("Running system: %s", args.system)
    system = Emulator(args, original_rom)
    _log_system_settings(system)

    # find the generator
    generator = get_generator(system.config.emulator, system.config.core)

    # a missing emulator: offer to install it, or go back to the frontend;
    # L1 and R1 held: offer to install it again (to update it)
    if not ensure_emulator(
        system.config.emulator,
        reinstall=getattr(args, "reinstall_emulator", False),
    ):
        return 0

    # a BIOS the emulator can't run without: stop here and say which one
    if not configure_emulator(original_rom):
        require_bios(args.system, system.config.emulator, effective_core(system))

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

        # no screen blanking, locking or sleep while the game runs (a game
        # played with a controller only looks idle to most desktops)
        with inhibit_idle(f"Playing {Path(session.args.rom).stem}"):
            # run a script before emulator starts
            call_game_hooks(session, "on-start-game")

            exit_code = _run_emulator(session)
            # the game is over: the overlay keeps away until the launcher is done
            set_phase(Phase.ENDING)

        # run a script after emulator shuts down
        call_game_hooks(session, "on-close-game")
        return exit_code
    finally:
        set_phase(Phase.ENDING)
        clear_state()
        SESSION_PAD_PROFILE.unlink(missing_ok=True)
        restore_power_profile(previous_power_profile)
        ES_GAME_INFO.unlink(missing_ok=True)


def _session_pad_profile(session: GameSession) -> Path | None:
    """Compose the game's pad profile (its own mappings plus the standard hotkeys).

    The overlay's input daemon maps the controllers with it while the game
    runs, once session.json names it (see _publish_state()).
    """
    system = session.system
    if session.generator.hotkeys_opt_in() and not overlay_enabled(system):
        return None
    base = find_profile(
        session.rom, session.args.system, system.config.emulator, effective_core(system)
    )
    return build_session_profile(session.generator, system, base, SESSION_PAD_PROFILE)


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


def _publish_state(
    session: GameSession, control: control_channel.Control, pad_profile: Path | None
) -> Callable[[subprocess.Popen[bytes]], None]:
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
    savestates = generator.savestates(system, session.rom) if control.has_slots() else None
    description = control.describe()

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
                game_info=str(ES_GAME_INFO),
                menu_theme=str(ES_MENU_THEME),
                control=description,
                savestates=savestates,
                overlay=overlay_enabled(system),
                osk=osk_enabled(system),
                pad_profile=str(pad_profile) if pad_profile else None,
                achievements=achievements.session_account(system.config),
            )
        )
        # the overlay may open from now on
        set_phase(Phase.RUNNING)

    return on_started


def _control(session: GameSession, cmd: Command) -> control_channel.Control:
    """The control channel's view of the emulator about to run."""
    system = session.system
    savestates = session.generator.savestates(system, session.rom) or {}
    slot = savestates.get("slot", 0)
    return control_channel.Control(
        bindings=effective_bindings(session.generator, system),
        osk=osk_enabled(system),
        pipe=cmd.stdin_fifo,
        pipe_commands=session.generator.pipe_commands(system),
        slot=slot if isinstance(slot, int) else 0,
        discs=control_channel.Discs.for_game(
            session.rom, SAVES, system.config.get_bool("disc_drive", False)
        ),
    )


def _run_emulator(session: GameSession) -> int:
    """Generate the emulator command, set up HUD and gun helpers, and run it."""
    system = session.system

    pad_profile = _session_pad_profile(session)

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

    control = _control(session, cmd)
    with profiler.pause(), control_channel.serve(control):
        session.inputs.monitor.start()
        return run_command(
            cmd,
            on_started=_publish_state(session, control, pad_profile),
            on_output=control.on_output,
        )
