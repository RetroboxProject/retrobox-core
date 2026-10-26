from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

class Command:
    def __init__(self, array: Sequence[str | Path], env: Mapping[str, str | Path | None] | None = None):
        self.array = list(array)
        self.env: dict[str, str | Path | None] = dict(env) if env else {}

    def __str__(self):
        strings: list[str] = []

        for varName, varValue in self.env.items():
            if varValue is None:
                continue  # unset sentinel — not part of the actual command line
            strings.append(f"{varName}={varValue}")

        strings.extend(f"{value}" for value in self.array)

        return " ".join(strings)