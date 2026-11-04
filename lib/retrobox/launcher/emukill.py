"""End the game being played: ``retrobox-emukill`` (``python3 -m retrobox.launcher.emukill``).

Retrobox's counterpart of ``batocera-es-swissknife --emukill``. It reads
``session.json`` (see ``game_state``) and, in this order:

1. sends SIGTERM to the processes marked by the game's ``exit_env``: the
   ones a running client started outside the launcher (a Steam, Heroic or
   Lutris game, its Wine/Proton processes and wineserver included);
2. sends SIGTERM to the game's process group (the emulator, or the wrapper
   that waits for the client's game);
3. kills with SIGKILL whatever is still there after ``exit_timeout``.

The client's processes go first so that the wrapper, which returns to the
frontend as soon as the game is gone, does not bring EmulationStation back
over a game that is still closing. SIGTERM lets emulators save and quit
cleanly; SIGKILL is only the last resort.

Nothing happens when no game is running, so a stray press in the frontend
is harmless, and a second press while the first one is working is ignored.
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
import signal
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Final

from retrobox.configgen.utils.logger import OK, setup_logging
from retrobox.paths import LOGS, RUNTIME_DIR

from .game_state import GameState, read_state

_logger = logging.getLogger(__name__)

_LOCK_FILE: Final = RUNTIME_DIR / "emukill.lock"
_POLL_SECONDS: Final = 0.1


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
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"/proc/{entry.name}/stat", encoding="utf-8") as source:
                stat = source.read()
        except OSError:
            continue
        # after the command name: state ppid pgrp ...
        fields = stat[stat.rfind(")") + 2:].split()
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] != "Z":
            return True
    return False


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
            end_game(state)
            _logger.log(OK, "game ended")
        finally:
            os.close(lock)
    return 0


if __name__ == "__main__":
    sys.exit(main())
