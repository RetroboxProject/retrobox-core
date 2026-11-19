"""Retrobox project startup script.

Manages arguments, prepares the environment, generates configurations,
and launches the frontend (EmulationStation).

The ROM folder of every system is created if it is missing, with an
``_info.txt`` that says what goes in it (see retrobox.startup.frontend_conf.roms_dirs).

Installed PC games (Steam, Heroic, Lutris) are synced into their
EmulationStation ROM directories before startup as retrobox.ini says
([core] steam_sync, heroic_sync, lutris_sync: none, on-base-dir or
follow-roms-dir; none by default). If EmulationStation has no theme at all,
the default one is downloaded first, and so are the default bezels and
shaders the first time they are on offer (see retrobox.startup.downloads),
showing the progress on the overlay's task screen (without the overlay installed,
nothing is downloaded).

While EmulationStation runs, so does the overlay's input daemon
(``retrobox-inputd``, when the overlay is installed; a systemd user unit
where there is one, see retrobox.startup.input_daemon): it opens Retrobox's
overlay when a controller's hotkey is held, in a game or not, and maps the
game's controllers to keys while a game runs.

Every argument is forwarded to EmulationStation untouched (``retrobox --
ARGS...``). Before anything else, what Retrobox needs is checked and what is
missing is reported (see retrobox.doctor.startup_warnings), without stopping.
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
    ES_GAME_INFO,
    ES_INI_CFG,
    ES_INI_TMP,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    ES_WM_CLASS,
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
from retrobox.doctor import startup_warnings
from retrobox.launcher.hooks import call_retrohook
from retrobox.startup.frontend_conf.audio_settings import ensure_audio_mixer
from retrobox.startup.frontend_conf.es_ini_generator import (
    ensure_ini_directories,
    generate_emulationstation_ini,
)
from retrobox.startup.frontend_conf.features_list_generator import generate_es_features
from retrobox.startup.frontend_conf.system_list_generator import generate_es_systems
from retrobox.startup.frontend_conf.pcgames_utils import sync_pcgames
from retrobox.startup.frontend_conf.quit_menu import apply_quit_menu
from retrobox.startup.frontend_conf.roms_dirs import create_roms_dirs
from retrobox.startup.downloads import install_all, labels, pending
from retrobox.startup.input_daemon import start_input_daemon, stop_input_daemon
from retrobox.utils.overlay_task import EXIT_UNAVAILABLE, overlay_available, run_task

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
    # EmulationStation changes the volume through an ALSA mixer: make it the
    # sound server's one (it must be done before ES starts, it rewrites the file).
    ensure_audio_mixer()
    # What QUIT opens: the full quit menu or a "Really quit?" question.
    apply_quit_menu()


def download_before_start() -> None:
    """Download the default theme, bezels and shaders if due (see downloads.pending).

    The download runs on the overlay's task screen, so its progress is visible
    (and it can be cancelled). Without the overlay installed nothing is
    downloaded (``retrobox --download`` does it by hand); if it is there but
    cannot open a screen, it runs here, in the log.
    """
    keys = pending()
    if not keys:
        return
    if not overlay_available():
        _logger.info("retrobox-overlay is not installed: not downloading %s", labels(keys))
        return
    _logger.info("Downloading before starting: %s", labels(keys))
    status = run_task(
        labels(keys),
        LOGS / "retrobox-downloads.log",
        [sys.executable, "-m", "retrobox.startup.downloads", *keys],
        download=True,
    )
    if status == EXIT_UNAVAILABLE:
        _logger.warning("The task screen could not be shown: downloading without it")
        install_all(keys)


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

    download_before_start()

    # Force SDL2 to use the native Wayland backend instead of falling back
    # to XWayland/XRandR. "wayland,x11" keeps x11 as a fallback in case the
    # Wayland backend fails to initialize for any reason.
    es_env = os.environ.copy()
    es_env["SDL_VIDEODRIVER"] = "wayland,x11"
    # Same window class whatever the binary is called, so that the desktop
    # entry (StartupWMClass) and the task bar recognise the window.
    es_env["SDL_VIDEO_X11_WMCLASS"] = ES_WM_CLASS
    es_env["SDL_VIDEO_WAYLAND_WMCLASS"] = ES_WM_CLASS
    # Controllers through the kernel's evdev devices, not SDL's HIDAPI drivers:
    # HIDAPI numbers the buttons of some pads (Switch, DualShock 4, DualSense)
    # its own way, and es_input.cfg (from which every emulator's controls are
    # written) must use the numbering of evdev, which RetroArch's udev driver
    # and the overlay (its menu and its input daemon) read. Everything started from EmulationStation
    # inherits it; the emulators that want HIDAPI (Dolphin, Eden, Ryujinx...)
    # turn it back on in their generator, with their own controller ids.
    es_env["SDL_JOYSTICK_HIDAPI"] = "0"

    _logger.info("Starting EmulationStation")

    input_daemon = start_input_daemon(es_env)
    try:
        result = subprocess.run(
            [str(ES_EXECUTABLE), "--fullscreen-borderless", "--home", str(FRONTEND_HOME),
             *map(str, args)],
            cwd=str(FRONTEND_DIR),
            env=es_env,
            check=False,
        )
    finally:
        stop_input_daemon(input_daemon)

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
        ES_GAME_INFO,
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

def main() -> int:
    """Run the Retrobox startup script, logging to stdout/stderr and
    LOGS/retrobox-startup.log.

    See _main() for what it does.
    """
    with setup_logging(LOGS / "retrobox-startup.log"):
        return _main()


def _main() -> int:
    """Run the main entry point for the Retrobox startup script.

    Reports what is missing (see startup_warnings()), syncs the installed PC
    games as retrobox.ini says (see sync_pcgames()) and passes every argument
    straight through to the "emulationstation" binary.

    Returns:
        The exit code of the application.
    """

    signal.signal(signal.SIGTERM, _handle_sigterm)

    args = sys.argv[1:]
    for warning in startup_warnings():
        _logger.warning("%s", warning)

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

    create_roms_dirs()

    try:
        return run_emulationstation(args)
    finally:
        teardown()


if __name__ == "__main__":
    raise SystemExit(main())
