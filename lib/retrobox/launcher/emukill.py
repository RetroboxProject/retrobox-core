"""End the game being played: ``retrobox-emukill`` (``python3 -m retrobox.launcher.emukill``).

Retrobox's counterpart of ``batocera-es-swissknife --emukill``. It reads
``session.json`` (see ``game_state``) and, in this order:

1. asks the game's windows to close, as the X button of the window does
   (through the window manager: ``wmctrl -c`` on X11, ``wlrctl`` on Wayland),
   and gives the game a few seconds to quit on its own: that is the way out
   every emulator handles, the one that saves and flushes (no key is pressed,
   so an emulator that grabs Alt+F4 cannot get in the way);
2. sends SIGTERM to the processes marked by the game's ``exit_env``: the
   ones a running client started outside the launcher (a Steam, Heroic or
   Lutris game, its Wine/Proton processes and wineserver included);
3. sends SIGTERM to the game's process group (the emulator, or the wrapper
   that waits for the client's game);
4. kills with SIGKILL whatever is still there after ``exit_timeout``.

The client's processes go first so that the wrapper, which returns to the
frontend as soon as the game is gone, does not bring EmulationStation back
over a game that is still closing. SIGTERM is the second chance (SDL
programs turn it into a quit; others die at once); SIGKILL is the last resort.

It first moves the launch to ``ending`` (see ``launch_phase``): the overlay
closes and stays away until the launcher is done.

Nothing happens when no game is running, so a stray press in the frontend
is harmless, and a second press while the first one is working is ignored.
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import Final

from retrobox.configgen.utils.logger import OK, setup_logging
from retrobox.paths import LOGS, RUNTIME_DIR

from .game_state import GameState, read_state
from .launch_phase import Phase, set_phase

_logger = logging.getLogger(__name__)

_LOCK_FILE: Final = RUNTIME_DIR / "emukill.lock"
_POLL_SECONDS: Final = 0.1
# how long the game has to quit after its windows are asked to close
CLOSE_GRACE: Final = 3.0
# a window manager's answer to wmctrl or wlrctl is quick; never wait longer
_TOOL_TIMEOUT: Final = 2.0


def _environ(pid: int) -> dict[bytes, bytes]:
    """Environment of a process; empty when it is gone or belongs to someone else."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as source:
            raw = source.read()
    except OSError:
        return {}
    pairs = (item.partition(b"=") for item in raw.split(b"\0") if item)
    return {name: value for name, _, value in pairs}


def find_env_processes(exit_env: Mapping[str, Sequence[str]]) -> set[int]:
    """Pids of the processes whose environment matches any entry of ``exit_env``."""
    wanted = {
        name.encode(): {value.encode() for value in values}
        for name, values in exit_env.items()
        if values
    }
    if not wanted:
        return set()

    own = os.getpid()
    found: set[int] = set()
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit() or int(entry.name) == own:
            continue
        environ = _environ(int(entry.name))
        if any(environ.get(name) in values for name, values in wanted.items()):
            found.add(int(entry.name))
    return found


def _signal_pids(pids: Iterable[int], sig: signal.Signals) -> set[int]:
    """Send a signal to every pid; return the ones that still existed."""
    reached = set()
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            continue
        except PermissionError:
            _logger.warning("not allowed to signal pid %d", pid)
            continue
        reached.add(pid)
    return reached


def _group_exists(pgid: int) -> bool:
    """Tell whether a live (not zombie) process is still in the group.

    ``killpg(pgid, 0)`` is not enough: it also succeeds while only zombies
    are left, and those wait for a parent that may take its time.
    """
    return bool(_group_pids(pgid))


def _group_pids(pgid: int) -> set[int]:
    """Pids of the live (not zombie) processes of a process group."""
    # after the command name in /proc/PID/stat: state ppid pgrp ...
    pids = set()
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"/proc/{entry.name}/stat", encoding="utf-8") as source:
                stat = source.read()
        except OSError:
            continue
        fields = stat[stat.rfind(")") + 2:].split()
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] != "Z":
            pids.add(int(entry.name))
    return pids


def windows_of(listing: str, pids: Collection[int]) -> list[str]:
    """Ids of the windows of ``pids`` in the output of ``wmctrl -lp``.

    A line is ``<id> <desktop> <pid> <host> <title>``; a window of no process
    (pid 0) or of another one is not the game's.
    """
    ids = []
    for line in listing.splitlines():
        fields = line.split(None, 3)
        if len(fields) >= 3 and fields[2].isdigit() and int(fields[2]) in pids:
            ids.append(fields[0])
    return ids


def _run(argv: Sequence[str], env: Mapping[str, str]) -> subprocess.CompletedProcess[str] | None:
    """Run a window tool: its result, or None when it is missing, fails to start or hangs."""
    try:
        return subprocess.run(
            argv, env=dict(env), capture_output=True, text=True, check=False, timeout=_TOOL_TIMEOUT
        )
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("%s: %s", argv[0], err)
        return None


def _close_x11_windows(pids: Collection[int], env: Mapping[str, str]) -> int:
    """Ask the windows of ``pids`` to close (EWMH ``_NET_CLOSE_WINDOW``); how many."""
    if not shutil.which("wmctrl"):
        return 0
    listing = _run(["wmctrl", "-lp"], env)
    if listing is None or listing.returncode != 0:
        return 0
    asked = 0
    for window in windows_of(listing.stdout, pids):
        result = _run(["wmctrl", "-ic", window], env)
        asked += int(result is not None and result.returncode == 0)
    return asked


def _close_wayland_window(env: Mapping[str, str]) -> int:
    """Ask the focused window to close, through the compositor; how many.

    Wayland tells nobody which process owns a window, so this is the one that
    has the focus: the game's, as the overlay is away while the game ends.
    """
    if not shutil.which("wlrctl"):
        return 0
    result = _run(["wlrctl", "window", "close", "state:focused"], env)
    return int(result is not None and result.returncode == 0)


def _session_env() -> dict[str, str]:
    """The environment to reach the display with: the caller's, with the usual
    places of the console's session for what a service (the input daemon) lacks."""
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    return env


def ask_windows_to_close(state: GameState) -> int:
    """Ask the game's windows to close, the way the window's X button does.

    Returns how many requests were accepted (0: nothing was asked, the signals
    are next). X11 first, by process (XWayland windows included); on Wayland a
    native window is only known as the focused one.
    """
    env = _session_env()
    pids = _group_pids(state.pgid) | find_env_processes(state.exit_env)
    asked = _close_x11_windows(pids, env) if pids else 0
    if not asked and os.path.exists(f"{env['XDG_RUNTIME_DIR']}/{env['WAYLAND_DISPLAY']}"):
        asked = _close_wayland_window(env)
    return asked


def _game_gone(state: GameState) -> bool:
    """Whether no process of the game is left."""
    return not find_env_processes(state.exit_env) and not _group_exists(state.pgid)


def _wait(gone: Callable[[], bool], deadline: float) -> bool:
    """Poll until ``gone()`` is true or the deadline passes; return ``gone()``."""
    while not gone():
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_SECONDS)
    return True


def _end_env_processes(state: GameState, deadline: float) -> None:
    """Stop the game's processes started outside the launcher."""
    pids = _signal_pids(find_env_processes(state.exit_env), signal.SIGTERM)
    if not pids:
        return
    _logger.info("SIGTERM sent to %d process(es) of the game: %s", len(pids), sorted(pids))
    if _wait(lambda: not find_env_processes(state.exit_env), deadline):
        return
    # rescanned: a launcher may have started more of them meanwhile
    left = _signal_pids(find_env_processes(state.exit_env), signal.SIGKILL)
    _logger.warning("SIGKILL sent to %d process(es) still running: %s", len(left), sorted(left))


def _end_process_group(state: GameState, deadline: float) -> None:
    """Stop the emulator (or the wrapper) and everything in its process group."""
    if not _group_exists(state.pgid):
        return
    try:
        os.killpg(state.pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    _logger.info("SIGTERM sent to process group %d (%s)", state.pgid, state.emulator)
    if _wait(lambda: not _group_exists(state.pgid), deadline):
        return
    try:
        os.killpg(state.pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    _logger.warning("SIGKILL sent to process group %d", state.pgid)


def end_game(state: GameState) -> None:
    """Stop every process of the game, gently first."""
    if ask_windows_to_close(state):
        _logger.info("windows asked to close; %.0f s for the game to quit", CLOSE_GRACE)
        if _wait(lambda: _game_gone(state), time.monotonic() + CLOSE_GRACE):
            return
        _logger.info("the game is still there: signals")
    deadline = time.monotonic() + state.exit_timeout
    _end_env_processes(state, deadline)
    # the group gets a full timeout of its own: its wrapper may only now be
    # noticing that the game is gone
    _end_process_group(state, max(deadline, time.monotonic() + state.exit_timeout))


def _take_lock() -> int | None:
    """Hold the emukill lock; None when another emukill already holds it."""
    fd = os.open(_LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as err:
        os.close(fd)
        if err.errno in (errno.EAGAIN, errno.EACCES):
            return None
        raise
    return fd


def main() -> int:
    """Entry point; returns the exit status."""
    with setup_logging(LOGS / "retrobox-emukill.log"):
        state = read_state()
        if state is None or not state.is_alive():
            _logger.info("no game running: nothing to do")
            return 0

        lock = _take_lock()
        if lock is None:
            _logger.info("already ending the game")
            return 0
        try:
            _logger.info("ending %s (%s, %s)", state.rom, state.system, state.emulator)
            # the overlay closes and stays away until the launcher is done
            set_phase(Phase.ENDING, state.launcher_pid)
            end_game(state)
            _logger.log(OK, "game ended")
        finally:
            os.close(lock)
    return 0


if __name__ == "__main__":
    sys.exit(main())
