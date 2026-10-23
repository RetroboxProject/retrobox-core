#!/usr/bin/env python3
"""Retrobox project startup script.

Manages arguments, prepares the environment, generates configurations,
and launches the frontend (EmulationStation).

Accepts one flag of its own, "--pcgames-sync", which enables syncing
installed PC games (Steam, Lutris, Heroic) into their EmulationStation
ROM directories before startup; without it, the sync is skipped. Any
other argument is forwarded to EmulationStation untouched.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import types
from pathlib import Path

_logger = logging.getLogger(__name__)

# Global flag to ensure teardown runs only once
_TEARDOWN_DONE: bool = False

# Resolve root directory safely, ensuring it is always a Path object
_RETROBOX_ROOTDIR: Path = Path(
    os.environ.get("RETROBOX_ROOTDIR", str(Path(__file__).resolve().parents[2]))
)

# Ensure the project root and runtime directories are in the Python path
# before importing project-specific modules.
sys.path.insert(0, str(_RETROBOX_ROOTDIR))
sys.path.insert(0, str(_RETROBOX_ROOTDIR / "runtime"))
sys.path.insert(0, str(_RETROBOX_ROOTDIR / "runtime" / "launcher"))

# the paths are added to sys.path above, so pylint cannot tell first party imports
# pylint: disable=wrong-import-position,wrong-import-order
# retrobox.ini (layered: /etc/retrobox + ~/.config/retrobox) is loaded by
# runtime.paths._base at import time, BEFORE its Final constants are
# computed. No separate call is needed before this import.
from runtime.paths import (
    ES_EXECUTABLE,
    ES_FEATURES_CFG,
    ES_FEATURES_TMP,
    ES_INI_CFG,
    ES_INI_TMP,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    FRONTEND_DIR,
    FRONTEND_HOME,
    RETROBOX_ROOTDIR,
    ROMS,
    RUNTIME_DIR,
    THEMES_DIR,
    _USER_ES_DIR,
    DirectoryCreationError,
    mkdir_if_not_exists,
)
from runtime.launcher.launcher_lib.hooks import call_retrohook
from frontend_conf.es_ini_generator import generate_emulationstation_ini
from frontend_conf.features_list_generator import generate_es_features
from frontend_conf.system_list_generator import generate_es_systems
from frontend_conf.pcgames_utils import heroic_es_sync, lutris_es_sync, steam_es_sync
# pylint: enable=wrong-import-position,wrong-import-order


def is_emulationstation_running(es_binary: Path) -> bool:
    """
    Check if an EmulationStation process is already alive (from any
    Retrobox instance) by inspecting /proc directly.

    This avoids relying on a pidfile that could become stale (e.g., after
    a SIGKILL that bypasses teardown()).

    Args:
        es_binary: The Path to the EmulationStation binary to check against.

    Returns:
        True if a matching process is found, False otherwise.
    """
    current_pid = os.getpid()
    try:
        proc_entries = list(Path("/proc").iterdir())
    except (FileNotFoundError, PermissionError):
        return False

    for entry in proc_entries:
        if not entry.name.isdigit():
            continue

        pid = int(entry.name)
        if pid == current_pid:
            continue

        try:
            cmdline = (entry / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue

        if not cmdline:
            continue

        argv0 = cmdline.split(b"\0", 1)[0]
        if Path(argv0.decode(errors="replace")).name == es_binary.name:
            return True

    return False


def seed_user_es_dir() -> None:
    """
    Copy the default user-level EmulationStation files shipped with the
    install (frontend/.emulationstation, e.g. collections) into the user's
    EmulationStation home, without overwriting anything already there.

    The shipped copy is read-only; the writable home lives in the data
    directory. If both ever coincide (RETROBOX_DATADIR pointing at the
    frontend dir) there is nothing to copy.
    """
    seed_dir = FRONTEND_DIR / ".emulationstation"
    if not seed_dir.is_dir() or seed_dir.resolve() == _USER_ES_DIR.resolve():
        return

    for source in seed_dir.rglob("*"):
        if not source.is_file():
            continue
        target = _USER_ES_DIR / source.relative_to(seed_dir)
        if target.exists() or target.is_symlink():
            continue
        mkdir_if_not_exists(target.parent)
        shutil.copy2(source, target)


def setup_emulationstation_config() -> None:
    """
    Ensure the user's EmulationStation configuration directory exists
    and generate all necessary configuration files (ini, systems, features).
    """
    if not _USER_ES_DIR.is_dir():
        mkdir_if_not_exists(_USER_ES_DIR)
    seed_user_es_dir()
    # ES only honours the `themes=` key of emulationstation.ini if it exists.
    mkdir_if_not_exists(THEMES_DIR)

    generate_emulationstation_ini()
    generate_es_systems()
    generate_es_features()


def run_emulationstation(args: list[str]) -> int:
    """
    Execute the EmulationStation binary with the provided arguments.

    Args:
        args: List of command-line arguments to pass to EmulationStation.

    Returns:
        The return code of the EmulationStation process.
    """
    setup_emulationstation_config()

    call_retrohook(
        "_frontend",
        "emulationstation",
        "on-frontend-start",
        args,
    )

    if not ES_EXECUTABLE.is_file():
        _logger.error("EmulationStation binary not found at %s", ES_EXECUTABLE)
        return 1

    _logger.info("=========")

    # Force SDL2 to use the native Wayland backend instead of falling back
    # to XWayland/XRandR. "wayland,x11" keeps x11 as a fallback in case the
    # Wayland backend fails to initialize for any reason.
    es_env = os.environ.copy()
    es_env["SDL_VIDEODRIVER"] = "wayland,x11"

    result = subprocess.run(
        [str(ES_EXECUTABLE), "--home", str(FRONTEND_HOME), *map(str, args)],
        cwd=str(FRONTEND_DIR),
        env=es_env,
        check=False,
    )

    call_retrohook(
        "_frontend",
        "emulationstation",
        "on-frontend-stop",
        args,
    )

    return result.returncode


def teardown() -> None:
    """
    Clean up temporary files, symlinks, and runtime directories
    after EmulationStation exits. Ensures it only runs once.
    """
    global _TEARDOWN_DONE  # pylint: disable=global-statement
    if _TEARDOWN_DONE:
        return
    _TEARDOWN_DONE = True

    paths_to_clean = [
        ES_SYSTEMS_CFG,
        ES_FEATURES_CFG,
        ES_SYSTEMS_TMP,
        ES_FEATURES_TMP,
        ES_INI_CFG,
        ES_INI_TMP,
        Path("/tmp/game.xml"),
        Path("/tmp/emulationstation.ready"),
        Path("/tmp/gameoverlay_ui.txt"),
        Path("/tmp/env-launcher.txt"),
        RUNTIME_DIR,
    ]

    for path in paths_to_clean:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    # Clean up any leftover wrapper scripts in /tmp
    for wrapper_file in Path("/tmp").glob("*wrapper*.sh"):
        wrapper_file.unlink(missing_ok=True)


def _handle_sigterm(signum: int, frame: types.FrameType | None) -> None:
    """
    Signal handler for SIGTERM to ensure a clean exit with the
    appropriate status code.
    """
    raise SystemExit(128 + signum)

_PCGAMES_SYNC_FLAG = "--pcgames-sync"


def main() -> int:
    """Run the main entry point for the Retrobox startup script.

    Consumes the "--pcgames-sync" flag (if present) to decide whether to
    sync installed PC games (Steam, Lutris, Heroic) before starting the
    frontend; that flag is never forwarded to EmulationStation. Any other
    argument is passed straight through to the "emulationstation" binary.

    Returns:
        The exit code of the application.
    """

    signal.signal(signal.SIGTERM, _handle_sigterm)

    args = sys.argv[1:]
    do_pcgames_sync = _PCGAMES_SYNC_FLAG in args
    if do_pcgames_sync:
        args = [arg for arg in args if arg != _PCGAMES_SYNC_FLAG]

    if not RETROBOX_ROOTDIR.is_dir():
        _logger.error("Invalid Retrobox directory: %s", RETROBOX_ROOTDIR)
        return 1

    if is_emulationstation_running(ES_EXECUTABLE):
        _logger.error("Retrobox (EmulationStation) is already running.")
        return 1

    if do_pcgames_sync:
        try:
            steam_es_sync(ROMS / "steam")
            lutris_es_sync(ROMS / "lutris")
            heroic_es_sync(ROMS / "heroic")
        except DirectoryCreationError as exc:
            # Notification already sent by safe_mkdir; just exit cleanly.
            _logger.error("Aborting startup: %s", exc)
            return 1
    else:
        _logger.debug(
            "Skipping PC games sync (pass %s to enable it).", _PCGAMES_SYNC_FLAG
        )

    try:
        _logger.info("=========")
        return run_emulationstation(args)
    finally:
        teardown()


if __name__ == "__main__":
    raise SystemExit(main())
