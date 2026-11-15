"""The systems Retrobox knows, for choosing which ones to hide."""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from retrobox.paths import layered_files

try:
    _Loader = yaml.CSafeLoader
except AttributeError:  # PyYAML built without libyaml
    _Loader = yaml.SafeLoader  # type: ignore[misc]


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """One system definition of the ``systems`` folder."""

    name: str  # what [core] ignore_systems lists
    fullname: str
    manufacturer: str


def available_systems() -> list[SystemInfo]:
    """Every system of the (layered) systems, sorted by full name.

    A file that can't be read is skipped: it can't be listed in EmulationStation
    either.
    """
    found: dict[str, SystemInfo] = {}
    for path in layered_files("systems", "*.yaml").values():
        try:
            with path.open(encoding="utf-8") as handle:
                data = yaml.load(handle, Loader=_Loader)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict) or not data:
            continue
        name, content = next(iter(data.items()))
        content = content if isinstance(content, dict) else {}
        found[str(name).lower()] = SystemInfo(
            name=str(name).lower(),
            fullname=str(content.get("fullname") or name),
            manufacturer=str(content.get("manufacturer") or "").lstrip("_"),
        )
    return sorted(found.values(), key=lambda system: system.fullname.lower())
