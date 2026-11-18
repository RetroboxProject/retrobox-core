"""The BIOS files the systems need, and whether the BIOS folder has them.

Each system declares its BIOS in its own YAML (``share/systems/...``), under
``bios:``, a list of requirements. A requirement is met by any one of its
files: a single file, or the alternatives (regions, revisions) that all do
the job::

    bios:
    - name: PlayStation BIOS            # for messages (default: its file)
      one_of:
      - file: scph5501.bin              # relative to the BIOS folder
        md5: 490f666e1afb15b7362b406ed1cea246   # or a list; none: not checked
        note: USA
      - file: scph5500.bin
        md5: 8dd7d5296a650fac7319bce665a6a53c
      required_for: [libretro/swanstation, ares]
    - file: dc/dc_boot.bin              # a requirement of one file
      md5: e10c53c2f8b90bab96ead2d368858623
      optional: true

``required_for`` lists the emulators (``ares``) or cores (``libretro/swanstation``)
that can't run the system without it; with no list, all of them can't.
``optional: true`` marks a file that only improves something (an emulator has
a replacement of its own, or few games use it). A file may be a glob
(``pcsx2/bios/*.bin``) when any dump in a folder does.

This module is the only one that reads those declarations: the doctor, and
later the launcher and EmulationStation's BIOS menu, ask it. The MD5 of every
file it checks is cached by size and modification time, so a check only
reads the files that changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Final

from retrobox.paths import BIOS, CACHE

_logger = logging.getLogger(__name__)

_CACHE_FILE: Final = CACHE / "bios-md5.json"
_MD5: Final = re.compile(r"^[0-9a-f]{32}$")
_GLOB_CHARACTERS: Final = frozenset("*?[")
_FILE_KEYS: Final = frozenset({"file", "md5", "note"})
_REQUIREMENT_KEYS: Final = frozenset({"name", "one_of", "required_for", "optional", *_FILE_KEYS})
_READ_CHUNK: Final = 1024 * 1024


class BiosError(ValueError):
    """A ``bios:`` block that does not follow the format."""


@dataclass(frozen=True)
class BiosFile:
    """One file that meets a requirement."""

    path: str  # relative to the BIOS folder; may be a glob
    md5: tuple[str, ...] = ()  # the known good dumps; empty: any file does
    note: str = ""

    @property
    def is_glob(self) -> bool:
        """Whether ``path`` names several files (``pcsx2/bios/*.bin``)."""
        return bool(_GLOB_CHARACTERS & set(self.path))


@dataclass(frozen=True)
class Requirement:
    """A BIOS a system needs: any one of ``files`` meets it."""

    system: str
    name: str
    files: tuple[BiosFile, ...]
    required_for: tuple[str, ...] | None = None  # None: every emulator
    optional: bool = False

    def required_by(self, emulator: str, core: str = "") -> bool:
        """Whether ``emulator`` (and ``core``) can't run the system without it."""
        if self.optional:
            return False
        if self.required_for is None:
            return True
        return emulator in self.required_for or f"{emulator}/{core}" in self.required_for


class State(StrEnum):
    """Whether the BIOS folder meets a requirement."""

    FOUND = "found"  # a file with a known MD5 (or any, when none is known)
    WRONG = "wrong"  # files are there, but none with a known MD5
    MISSING = "missing"


@dataclass(frozen=True)
class Result:
    """A requirement, checked: the good files found, or the wrong ones."""

    requirement: Requirement
    state: State
    files: tuple[Path, ...] = ()


## Reading the declarations -----------------------------------------------


def _strings(value: Any, what: str) -> tuple[str, ...]:
    if value is None:
        return ()
    values = value if isinstance(value, list) else [value]
    if not all(isinstance(item, str) for item in values):
        raise BiosError(f"{what} must be a string or a list of strings")
    return tuple(values)


def _bios_file(entry: Mapping[str, Any], system: str) -> BiosFile:
    path = entry.get("file")
    if not isinstance(path, str) or not path:
        raise BiosError(f"{system}: every BIOS needs a 'file'")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise BiosError(f"{system}: {path} must be inside the BIOS folder")
    md5 = tuple(value.lower() for value in _strings(entry.get("md5"), f"{system}: md5 of {path}"))
    bad = [value for value in md5 if not _MD5.match(value)]
    if bad:
        raise BiosError(f"{system}: {path} has an invalid md5: {', '.join(bad)}")
    return BiosFile(path, md5, str(entry.get("note") or ""))


def _requirement(entry: Any, system: str) -> Requirement:
    if not isinstance(entry, dict):
        raise BiosError(f"{system}: each entry of 'bios' must be a mapping")
    unknown = set(entry) - _REQUIREMENT_KEYS
    if unknown:
        raise BiosError(f"{system}: unknown keys in 'bios': {', '.join(sorted(unknown))}")
    if "one_of" in entry:
        if _FILE_KEYS & set(entry):
            raise BiosError(f"{system}: an entry has either 'file' or 'one_of', not both")
        alternatives = entry["one_of"]
        if not isinstance(alternatives, list) or not alternatives:
            raise BiosError(f"{system}: 'one_of' must be a list of files")
        for alternative in alternatives:
            if not isinstance(alternative, dict) or set(alternative) - _FILE_KEYS:
                raise BiosError(f"{system}: the files of 'one_of' only take {sorted(_FILE_KEYS)}")
        files = tuple(_bios_file(alternative, system) for alternative in alternatives)
    else:
        files = (_bios_file(entry, system),)
    required_for = entry.get("required_for")
    return Requirement(
        system=system,
        name=str(entry.get("name") or files[0].path),
        files=files,
        required_for=None if required_for is None
        else _strings(required_for, f"{system}: required_for"),
        optional=bool(entry.get("optional", False)),
    )


def parse(system: str, content: Mapping[str, Any]) -> list[Requirement]:
    """The requirements in the ``bios:`` block of a system's settings.

    Raises:
        BiosError: When the block does not follow the format.
    """
    block = content.get("bios")
    if block is None:
        return []
    if not isinstance(block, list):
        raise BiosError(f"{system}: 'bios' must be a list")
    return [_requirement(entry, system) for entry in block]


def emulator_refs(content: Mapping[str, Any]) -> list[str]:
    """Every ``emulator`` and ``emulator/core`` a system's settings offer."""
    refs = []
    for emulator, data in (content.get("emulators") or {}).items():
        refs.append(emulator)
        cores = data.get("cores") if isinstance(data, dict) else None
        refs.extend(f"{emulator}/{core}" for core in (cores or {}))
    return refs


def default_emulator(content: Mapping[str, Any]) -> tuple[str, str]:
    """The emulator and core a system runs with, unless the user picks another."""
    first: tuple[str, str] | None = None
    for emulator, data in (content.get("emulators") or {}).items():
        cores = (data.get("cores") if isinstance(data, dict) else None) or {}
        for core, settings in cores.items():
            first = first or (emulator, core)
            if isinstance(settings, dict) and settings.get("default") is True:
                return emulator, core
        first = first or (emulator, "")
    return first or ("", "")


def load_requirements(
    systems: Iterable[tuple[str, Mapping[str, Any]]] | None = None,
) -> dict[str, list[Requirement]]:
    """The requirements of every system that declares some.

    Args:
        systems: (name, settings) of the systems; None: every system of the
            configuration layers. A system whose block is malformed is logged
            and left out.
    """
    if systems is None:
        # pylint: disable-next=import-outside-toplevel  # yaml, only when needed
        from retrobox.startup.frontend_conf.system_list_generator import load_systems

        systems = load_systems()
    requirements = {}
    for name, content in systems:
        try:
            found = parse(name, content)
        except BiosError as error:
            _logger.error("Ignoring the BIOS of %s: %s", name, error)
            continue
        if found:
            requirements[name] = found
    return requirements


## Checking the BIOS folder ------------------------------------------------


class _Md5Cache:
    """The MD5 of the files checked before, by path, size and modification time."""

    def __init__(self, path: Path = _CACHE_FILE) -> None:
        self._path = path
        self._entries: dict[str, list[Any]] = {}
        self._changed = False
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._entries = loaded
        except (OSError, ValueError):
            pass

    def md5(self, file: Path) -> str:
        """The MD5 of ``file``, read only when it changed since the last time."""
        stat = file.stat()
        key = str(file)
        cached = self._entries.get(key)
        if isinstance(cached, list) and cached[:2] == [stat.st_size, stat.st_mtime_ns]:
            return str(cached[2])
        digest = hashlib.md5(usedforsecurity=False)
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(_READ_CHUNK), b""):
                digest.update(block)
        value = digest.hexdigest()
        self._entries[key] = [stat.st_size, stat.st_mtime_ns, value]
        self._changed = True
        return value

    def save(self) -> None:
        """Write the cache back, if anything was added (best effort)."""
        if not self._changed:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._entries), encoding="utf-8")
            os.replace(temporary, self._path)
        except OSError as error:
            _logger.debug("Could not save the BIOS MD5 cache: %s", error)


def _candidates(file: BiosFile, folder: Path) -> list[Path]:
    if file.is_glob:
        return sorted(path for path in folder.glob(file.path) if path.is_file())
    path = folder / file.path
    return [path] if path.is_file() else []


def _check(requirement: Requirement, folder: Path, cache: _Md5Cache) -> Result:
    good: list[Path] = []
    wrong: list[Path] = []
    for file in requirement.files:
        for path in _candidates(file, folder):
            try:
                valid = not file.md5 or cache.md5(path) in file.md5
            except OSError:
                valid = False
            (good if valid else wrong).append(path)
    if good:
        return Result(requirement, State.FOUND, tuple(good))
    if wrong:
        return Result(requirement, State.WRONG, tuple(wrong))
    return Result(requirement, State.MISSING)


def check(requirements: Iterable[Requirement], folder: Path = BIOS) -> list[Result]:
    """Check each requirement against the BIOS folder."""
    cache = _Md5Cache()
    try:
        return [_check(requirement, folder, cache) for requirement in requirements]
    finally:
        cache.save()
