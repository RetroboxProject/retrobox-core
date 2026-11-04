"""The game currently running, published in ``<runtime dir>/session.json``.

The launcher writes the file once the emulator has started and removes it
when the game is over. Whatever acts on the running game from outside the
launcher reads it: ``retrobox-emukill`` (to end the game), the gamepad
mappers and the in-game overlay. It is the contract between them, so the
layout is versioned (``version``) and only ever extended.

``pid`` is the first process of the game (the emulator, or the wrapper that
runs it) and the leader of a process group of its own (``pgid``), so the
whole tree it starts can be signalled at once. ``start_time`` (from
``/proc/<pid>/stat``) tells it apart from a later process that reused the
pid. Games started by a client that already runs (Steam, Heroic, Lutris)
are not in that group: ``exit_env`` lists the environment variables, and
their values, that mark their processes.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

from retrobox.paths import RUNTIME_DIR

_logger = logging.getLogger(__name__)

SESSION_FILE: Final = RUNTIME_DIR / "session.json"
SESSION_VERSION: Final = 1

DEFAULT_EXIT_TIMEOUT: Final = 5.0
"""Seconds a game has to quit after SIGTERM before it is killed."""


def process_start_time(pid: int) -> int | None:
    """Start time of a process in clock ticks since boot, or None if it is gone."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # the command name (field 2) may hold spaces and parentheses: split after it
    fields = stat[stat.rfind(")") + 2:].split()
    try:
        return int(fields[19])  # field 22 of proc_pid_stat(5)
    except (IndexError, ValueError):
        return None


@dataclass
class GameState:  # pylint: disable=too-many-instance-attributes
    """What session.json says about the game being played."""

    pid: int
    pgid: int
    start_time: int
    launcher_pid: int
    system: str
    emulator: str
    core: str
    rom: str
    metadata: dict[str, str] = field(default_factory=dict)
    exit_timeout: float = DEFAULT_EXIT_TIMEOUT
    exit_env: dict[str, list[str]] = field(default_factory=dict)
    version: int = SESSION_VERSION

    def is_alive(self) -> bool:
        """Tell whether the game's first process is still the one that was started."""
        return process_start_time(self.pid) == self.start_time

    def to_json(self) -> str:
        """The JSON document written to session.json."""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_mapping(cls, data: dict) -> GameState:
        """Build a state from a parsed session.json; unknown keys are ignored."""
        known = set(cls.__dataclass_fields__)  # pylint: disable=no-member
        return cls(**{key: value for key, value in data.items() if key in known})


def write_state(state: GameState, path: Path = SESSION_FILE) -> None:
    """Publish the state atomically: readers never see a half-written file."""
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".session-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(state.to_json())
        os.replace(tmp_name, path)
    except OSError as err:
        # the game runs anyway, only the outside helpers won't find it
        _logger.warning("cannot write %s: %s", path, err)


def read_state(path: Path = SESSION_FILE) -> GameState | None:
    """The state of the running game, or None when there is none (or it is unreadable)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return GameState.from_mapping(data)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as err:
        _logger.warning("cannot read %s: %s", path, err)
        return None


def clear_state(path: Path = SESSION_FILE) -> None:
    """Remove the state of a game that is over."""
    path.unlink(missing_ok=True)
