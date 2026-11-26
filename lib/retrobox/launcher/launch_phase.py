"""Where the game launch is, published in ``<runtime dir>/launch.json``.

``retrobox-launch`` writes it as soon as it starts and removes it when it
exits, so it covers the whole launch, unlike ``session.json`` (which only
exists while the emulator runs)::

    {"version": 1, "pid": 4242, "start_time": 123456, "phase": "starting"}

The phase is ``starting`` while the game is being prepared (an emulator may
be installed first, on the overlay's task screen), ``running`` once the
emulator runs (see ``runner._publish_state()``), and ``ending`` once the game
is being closed: by ``retrobox-emukill``, or because the emulator quit. The
overlay (``retrobox-overlay`` and its input daemon) neither opens nor stays
open while a game is starting or ending: there is no menu to show then.

``pid`` is the launcher's and ``start_time`` (see
``game_state.process_start_time()``) tells it apart from a later process that
reused the pid: a file left by a launcher that died counts as no launch at
all. The layout is versioned (``version``) and only ever extended.

A frontend that is not a game (Kodi, see ``kodi_launch``) says so in
``frontend.json`` (``{"version": 1, "pid": ..., "start_time": ...}``, the same
meaning of ``pid`` and ``start_time``) for as long as it runs: the overlay does
not open over it, as long as no game session (``session.json``) is above it.
It is a file of its own because a game launched from the frontend writes and
removes ``launch.json`` for itself.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Final

from retrobox.paths import RUNTIME_DIR

from .game_state import process_start_time

_logger = logging.getLogger(__name__)

LAUNCH_FILE: Final = RUNTIME_DIR / "launch.json"
LAUNCH_VERSION: Final = 1
FRONTEND_FILE: Final = RUNTIME_DIR / "frontend.json"


class Phase(StrEnum):
    """Where the launch is."""

    STARTING = "starting"
    RUNNING = "running"
    ENDING = "ending"


def _read(path: Path) -> dict[str, object] | None:
    """The file's contents, or None when there is none (or it is unreadable)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as err:
        _logger.warning("cannot read %s: %s", path, err)
        return None
    return data if isinstance(data, dict) else None


def _write(data: dict[str, object], path: Path) -> None:
    """Write the file atomically: readers never see half of it."""
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".launch-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp)
        os.replace(tmp_name, path)
    except OSError as err:
        # the game runs anyway: only the overlay won't know where it is
        _logger.warning("cannot write %s: %s", path, err)


def start_launch(path: Path = LAUNCH_FILE) -> None:
    """This process starts a game launch."""
    pid = os.getpid()
    _write(
        {
            "version": LAUNCH_VERSION,
            "pid": pid,
            "start_time": process_start_time(pid) or 0,
            "phase": Phase.STARTING.value,
        },
        path,
    )


def set_phase(phase: Phase, launcher_pid: int | None = None, path: Path = LAUNCH_FILE) -> None:
    """Move the launch of ``launcher_pid`` (this process by default) to ``phase``.

    Nothing happens when the file belongs to another launch, or there is none.
    """
    data = _read(path)
    pid = os.getpid() if launcher_pid is None else launcher_pid
    if data is None or data.get("pid") != pid or data.get("phase") == phase.value:
        return
    _write({**data, "phase": phase.value}, path)


def end_launch(path: Path = LAUNCH_FILE) -> None:
    """This process's launch is over: remove the file, if it is still its."""
    data = _read(path)
    if data is not None and data.get("pid") == os.getpid():
        path.unlink(missing_ok=True)


def start_frontend(path: Path = FRONTEND_FILE) -> None:
    """This process is a frontend that is not a game (Kodi): no overlay over it."""
    pid = os.getpid()
    _write(
        {"version": LAUNCH_VERSION, "pid": pid, "start_time": process_start_time(pid) or 0},
        path,
    )


def end_frontend(path: Path = FRONTEND_FILE) -> None:
    """This process's frontend is over: remove the file, if it is still its."""
    data = _read(path)
    if data is not None and data.get("pid") == os.getpid():
        path.unlink(missing_ok=True)
