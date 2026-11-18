"""Find the executable of a standalone emulator, wherever it was installed.

Every generator of a standalone emulator describes its executable with an
:class:`EmulatorBinary` and asks it where the emulator is when a game starts.
The places are tried in this order, the first executable found wins:

1. Retrobox's own install, ``<emulators>/<folder>/app/`` (what the installers
   in ``tools/emulators/`` produce): ``bin/<name>`` and ``<name>`` (a source
   build, a release tarball, a sharun AppDir), then ``AppRun`` (an extracted
   AppImage), then ``usr/bin/<name>``.
2. The top of that folder: ``<name>`` and ``bin/<name>`` (portable
   emulators such as Redream and Supermodel, which keep their data next to
   the executable, and older layouts), and any ``*.AppImage`` directly in
   ``<emulators>/<folder>/`` or in its ``app/bin/``.
3. An AppImage the user downloaded into ``~/Applications``, ``~/AppImages``
   or ``~/.local/bin`` whose name starts with one of the emulator's names
   (``Cemu-2.6-x86_64.AppImage``); the newest one if there are several.
4. The distribution's package: the names on ``PATH``.

Flatpak installs are not looked for: a flatpak keeps its configuration under
``~/.var/app`` and only sees the folders it was granted, so the settings,
paths and environment configgen prepares for the game would not reach it.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from retrobox.configgen.exceptions import RetroboxException
from retrobox.paths import EMULATORS

if TYPE_CHECKING:
    from collections.abc import Iterator

# where people keep the AppImages they download (AppImageLauncher, Gear Lever...)
_USER_APPIMAGE_DIRS: Final = ("Applications", "AppImages", ".local/bin")

_APPIMAGE_SUFFIX: Final = ".appimage"


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _appimages(directory: Path, prefixes: tuple[str, ...] = ()) -> list[Path]:
    """The executable AppImages of ``directory`` (named after a prefix, if given), newest first."""
    if not directory.is_dir():
        return []
    found = []
    for entry in directory.iterdir():
        name = entry.name.lower()
        if not name.endswith(_APPIMAGE_SUFFIX) or not _is_executable(entry):
            continue
        if prefixes and not name.startswith(prefixes):
            continue
        found.append(entry)
    return sorted(found, key=lambda path: path.stat().st_mtime, reverse=True)


@dataclass(frozen=True)
class EmulatorBinary:
    """Where the executable of one emulator can be.

    Attributes:
        folder: Its folder under the emulators directory (``<emulators>/<folder>``).
        names: The names of its executable, preferred first. The first one
            also names its installer in messages unless ``installer`` is set.
        installer: The ``tools/emulators/<installer>.sh`` that installs it,
            if there is one ("" for none).
        appimage: Whether ``app/AppRun`` and AppImages count. False for an
            executable that must be a specific binary (an AppImage only
            starts the emulator's main program).
        outside: Whether the user's AppImages and the distribution's package
            count. False when the generator needs files of Retrobox's own
            install (RetroArch's cores and assets).
    """

    folder: str
    names: tuple[str, ...]
    installer: str = ""
    appimage: bool = True
    outside: bool = True

    @property
    def directory(self) -> Path:
        """``<emulators>/<folder>``, where Retrobox installs it."""
        return EMULATORS / self.folder

    def _in_folder(self, directory: Path) -> Iterator[Path]:
        app = directory / "app"
        for name in self.names:
            yield app / "bin" / name
            yield app / name
        if self.appimage:
            yield app / "AppRun"
        for name in self.names:
            yield app / "usr" / "bin" / name
        # portable emulators and older layouts of the same folder
        for name in self.names:
            yield directory / name
            yield directory / "bin" / name
        if self.appimage:
            yield from _appimages(directory)
            yield from _appimages(app / "bin")

    def _outside(self) -> Iterator[Path]:
        if self.appimage:
            prefixes = tuple(name.lower() for name in self.names)
            home = Path.home()
            for folder in _USER_APPIMAGE_DIRS:
                yield from _appimages(home / folder, prefixes)
        for name in self.names:
            if found := shutil.which(name):
                yield Path(found)

    def find_in(self, directory: Path) -> Path | None:
        """The executable inside ``directory`` (an install of it), or None."""
        return next((path for path in self._in_folder(directory) if _is_executable(path)), None)

    def find(self) -> Path | None:
        """The executable to run, or None when it is not installed anywhere."""
        if found := self.find_in(self.directory):
            return found
        if self.outside:
            return next((path for path in self._outside() if _is_executable(path)), None)
        return None

    def installed_by_retrobox(self) -> bool:
        """Whether Retrobox's own install (``<emulators>/<folder>``) has it."""
        return self.find_in(self.directory) is not None

    def hint(self) -> str:
        """How to install it, for an error message."""
        if self.installer:
            return f"install it with 'retrobox --install-emulator {self.installer}'"
        where = "your package manager"
        if self.appimage:
            where += " or an AppImage in ~/Applications"
        return f"install it with {where}, or put it in {self.directory / 'app'}"

    def require(self) -> Path:
        """The executable to run.

        Raises:
            RetroboxException: When it is not installed anywhere.
        """
        found = self.find()
        if found is None:
            raise RetroboxException(f"{self.names[0]} is not installed: {self.hint()}")
        return found

    @staticmethod
    def prefix_of(executable: Path) -> Path:
        """The install prefix of ``executable`` (``<prefix>/bin/<name>`` -> ``<prefix>``)."""
        parent = executable.resolve().parent
        return parent.parent if parent.name == "bin" else parent
