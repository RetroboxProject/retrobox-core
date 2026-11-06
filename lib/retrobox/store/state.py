"""What is installed: one manifest per package, in the state directory."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from retrobox.paths import CACHE, STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# package names are file names here: nothing but what pacman itself allows
_VALID_NAME = re.compile(r"^[a-z0-9@_+][a-z0-9@._+-]*$")

STORE_STATE_DIR = STATE_DIR / "store"
STORE_CACHE_DIR = CACHE / "store"


@dataclass
class Installed:
    """A package that is installed.

    Attributes:
        name: The package name.
        version: The installed version.
        files: Every file the package put in place, as absolute paths.
        batoexec: The ``.batoexec`` instructions of the package (``gamelist``
            entries to add to EmulationStation), kept to undo them on removal.
    """

    name: str
    version: str
    files: list[str] = field(default_factory=list)
    batoexec: list[str] = field(default_factory=list)


def is_valid_name(name: str) -> bool:
    """Whether a package name is safe to use as a file name."""
    return bool(_VALID_NAME.match(name))


class InstalledDatabase:
    """The manifests of the installed packages."""

    def __init__(self, directory: Path = STORE_STATE_DIR / "installed") -> None:
        self._directory = directory

    def _path(self, name: str) -> Path:
        if not is_valid_name(name):
            raise ValueError(f"invalid package name: {name!r}")
        return self._directory / f"{name}.json"

    def get(self, name: str) -> Installed | None:
        """The manifest of a package, or None if it is not installed."""
        if not is_valid_name(name):
            return None
        try:
            data: dict[str, Any] = json.loads(self._path(name).read_text(encoding="utf-8"))
            return Installed(
                name=str(data["name"]),
                version=str(data["version"]),
                files=[str(item) for item in data.get("files", [])],
                batoexec=[str(item) for item in data.get("batoexec", [])],
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError) as error:
            _logger.warning("unreadable manifest of %s: %s", name, error)
            return None

    def all(self) -> dict[str, Installed]:
        """Every installed package by name."""
        found: dict[str, Installed] = {}
        if not self._directory.is_dir():
            return found
        for path in sorted(self._directory.glob("*.json")):
            if (package := self.get(path.stem)) is not None:
                found[package.name] = package
        return found

    def save(self, package: Installed) -> None:
        """Write a manifest, replacing the previous one."""
        path = self._path(package.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.part")
        temporary.write_text(json.dumps(asdict(package), indent=1), encoding="utf-8")
        os.replace(temporary, path)

    def delete(self, name: str) -> None:
        """Forget a package."""
        self._path(name).unlink(missing_ok=True)
