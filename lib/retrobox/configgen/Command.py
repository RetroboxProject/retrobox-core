"""The command line a generator returns: what the launcher runs."""
# pylint: disable=invalid-name  # module name kept for its many importers

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path


class Command:  # pylint: disable=too-few-public-methods
    """An emulator's argv, its environment and, optionally, a command pipe."""

    def __init__(
        self,
        array: Sequence[str | Path],
        env: Mapping[str, str | Path | None] | None = None,
        stdin_fifo: Path | None = None,
    ):
        self.array = list(array)
        self.env: dict[str, str | Path | None] = dict(env) if env else {}
        # A named pipe the launcher creates and gives the emulator as its
        # standard input, for commands from outside (retrobox-overlay).
        self.stdin_fifo = stdin_fifo

    def __str__(self):
        strings: list[str] = []

        for name, value in self.env.items():
            if value is None:
                continue  # unset sentinel — not part of the actual command line
            strings.append(f"{name}={value}")

        strings.extend(f"{value}" for value in self.array)

        return " ".join(strings)
