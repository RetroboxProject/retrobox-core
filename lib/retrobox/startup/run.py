"""Retrobox project startup script.

Manages arguments, prepares the environment, generates configurations,
and launches the frontend (EmulationStation).

Installed PC games (Steam, Heroic, Lutris) are synced into their
EmulationStation ROM directories before startup as retrobox.ini says
([core] steam_sync, heroic_sync, lutris_sync: none, on-base-dir or
follow-roms-dir; none by default). If EmulationStation has no theme at all,
the default one is installed first.

Accepts one flag of its own, "--update-default-theme", which downloads the
default theme again (updating or reinstalling it) before startup. Every
other argument is forwarded to EmulationStation untouched, except the
retired "--pcgames-sync" flag, which is dropped with a warning.
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

# retrobox.ini (layered: /etc/retrobox + ~/.config/retrobox) is loaded by
# retrobox.paths._base at import time, BEFORE its Final constants are
# computed. No separate call is needed before this import.
from retrobox.paths import (
    ES_EXECUTABLE,
    ES_FEATURES_CFG,
    ES_FEATURES_TMP,
    ES_INI_CFG,
    ES_INI_TMP,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    FRONTEND_DIR,
    FRONTEND_HOME,
    LOGS,
    RETROBOX_ROOTDIR,
    RUNTIME_DIR,
    _USER_ES_DIR,
    DirectoryCreationError,
    mkdir_if_not_exists,
)
from retrobox.configgen.utils.logger import setup_logging
from retrobox.launcher.hooks import call_retrohook
from retrobox.startup.frontend_conf.es_ini_generator import (
    ensure_ini_directories,
    generate_emulationstation_ini,
)
from retrobox.startup.frontend_conf.features_list_generator import generate_es_features
from retrobox.startup.frontend_conf.system_list_generator import generate_es_systems
from retrobox.startup.frontend_conf.pcgames_utils import sync_pcgames
from retrobox.startup.frontend_conf.theme_bootstrap import ensure_default_theme

_logger = logging.getLogger(__name__)

# Global flag to ensure teardown runs only once
_TEARDOWN_DONE: bool = False


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
    # ES only honours a key of emulationstation.ini (log=, decorations=,
    # themes=...) if its directory already exists, so create them all first.
    ensure_ini_directories()

    generate_emulationstation_ini()
    generate_es_systems()
    generate_es_features()


def run_emulationstation(args: list[str], update_theme: bool = False) -> int:
    """
    Execute the EmulationStation binary with the provided arguments.

    Args:
        args: List of command-line arguments to pass to EmulationStation.
        update_theme: Download the default theme again before starting.

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

    ensure_default_theme(update=update_theme)

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
        RUNTIME_DIR,
    ]

    for path in paths_to_clean:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)



def _handle_sigterm(signum: int, frame: types.FrameType | None) -> None:
    """
    Signal handler for SIGTERM to ensure a clean exit with the
    appropriate status code.
    """
    raise SystemExit(128 + signum)

# Replaced by the [core] *_sync keys of retrobox.ini; still dropped so that
# old shortcuts don't pass it on to EmulationStation.
_RETIRED_PCGAMES_SYNC_FLAG = "--pcgames-sync"
_UPDATE_THEME_FLAG = "--update-default-theme"


def main() -> int:
    """Run the Retrobox startup script, logging to stdout/stderr and
    LOGS/retrobox-startup.log.

    See _main() for what it does.
    """
    with setup_logging(LOGS / "retrobox-startup.log"):
        return _main()


def _main() -> int:
    """Run the main entry point for the Retrobox startup script.

    Syncs the installed PC games as retrobox.ini says (see sync_pcgames())
    and passes every argument straight through to the "emulationstation"
    binary, except "--update-default-theme" (consumed here) and the retired
    "--pcgames-sync".

    Returns:
        The exit code of the application.
    """

    signal.signal(signal.SIGTERM, _handle_sigterm)

    args = sys.argv[1:]
    update_theme = _UPDATE_THEME_FLAG in args
    if update_theme:
        args = [arg for arg in args if arg != _UPDATE_THEME_FLAG]
    if _RETIRED_PCGAMES_SYNC_FLAG in args:
        args = [arg for arg in args if arg != _RETIRED_PCGAMES_SYNC_FLAG]
        _logger.warning(
            "%s is gone: set steam_sync, heroic_sync and lutris_sync under [core] "
            "in retrobox.ini instead. Ignoring it.",
            _RETIRED_PCGAMES_SYNC_FLAG,
        )

    if not RETROBOX_ROOTDIR.is_dir():
        _logger.error("Invalid Retrobox directory: %s", RETROBOX_ROOTDIR)
        return 1

    if is_emulationstation_running(ES_EXECUTABLE):
        _logger.error("Retrobox (EmulationStation) is already running.")
        return 1

    try:
        sync_pcgames()
    except DirectoryCreationError as exc:
        # Notification already sent by safe_mkdir; just exit cleanly.
        _logger.error("Aborting startup: %s", exc)
        return 1

    try:
        _logger.info("=========")
        return run_emulationstation(args, update_theme=update_theme)
    finally:
        teardown()


if __name__ == "__main__":
    raise SystemExit(main())
