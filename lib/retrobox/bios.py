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
a replacement of its own, or few games use it). An optional file is reported
like any other one (the doctor and EmulationStation's missing BIOS check,
which asks before a game), but it never stops a game: only a file the
emulator really can't run without does. A file may be a glob
(``pcsx2/bios/*.bin``) when any dump in a folder does, and start with
``{roms}/`` for one an emulator also finds in the ROMs folder
(``{roms}/neogeo/neogeo.zip``), and ``min_size`` (in
bytes) counts the files too small to be one as missing, when there is no MD5
to check.

This module is the only one that reads those declarations: the doctor asks
it about every system, and the launcher, through require(), about the game
it starts, which stops with a RetroboxException (EmulationStation shows its
message) when a BIOS the emulator needs is missing. The MD5 of every file it
checks is cached by size and modification time, so a check only reads the
files that changed.
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

from retrobox.configgen.exceptions import RetroboxException
from retrobox.paths import BIOS, CACHE, CONFIG_LAYERS, ROMS

_logger = logging.getLogger(__name__)

_CACHE_FILE: Final = CACHE / "bios-md5.json"
_MD5: Final = re.compile(r"^[0-9a-f]{32}$")
_GLOB_CHARACTERS: Final = frozenset("*?[")
_FILE_KEYS: Final = frozenset({"file", "md5", "note", "min_size"})
_REQUIREMENT_KEYS: Final = frozenset({"name", "one_of", "required_for", "optional", *_FILE_KEYS})
_READ_CHUNK: Final = 1024 * 1024
_ROMS_PREFIX: Final = "{roms}/"


class BiosError(ValueError):
    """A ``bios:`` block that does not follow the format."""


@dataclass(frozen=True)
class BiosFile:
    """One file that meets a requirement."""

    path: str  # relative to the BIOS folder (or to the ROMs one: {roms}/...); may be a glob
    md5: tuple[str, ...] = ()  # the known good dumps; empty: any file does
    note: str = ""
    min_size: int = 0  # bytes; a smaller file is not a dump

    @property
    def in_roms(self) -> bool:
        """Whether ``path`` is in the ROMs folder rather than in the BIOS one."""
        return self.path.startswith(_ROMS_PREFIX)

    @property
    def relative(self) -> str:
        """``path`` without its ``{roms}/``."""
        return self.path.removeprefix(_ROMS_PREFIX)

    def location(self, folder: Path) -> Path:
        """Where it is: ``folder`` (the BIOS one) or the ROMs folder, plus ``relative``."""
        return (ROMS if self.in_roms else folder) / self.relative

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
    pure = PurePosixPath(path.removeprefix(_ROMS_PREFIX))
    if pure.is_absolute() or ".." in pure.parts or "{" in str(pure):
        raise BiosError(f"{system}: {path} must be inside the BIOS (or {{roms}}) folder")
    md5 = tuple(value.lower() for value in _strings(entry.get("md5"), f"{system}: md5 of {path}"))
    bad = [value for value in md5 if not _MD5.match(value)]
    if bad:
        raise BiosError(f"{system}: {path} has an invalid md5: {', '.join(bad)}")
    min_size = entry.get("min_size", 0)
    if not isinstance(min_size, int) or isinstance(min_size, bool) or min_size < 0:
        raise BiosError(f"{system}: min_size of {path} must be a number of bytes")
    return BiosFile(path, md5, str(entry.get("note") or ""), min_size)


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


def _big_enough(path: Path, min_size: int) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= min_size
    except OSError:
        return False


def _candidates(file: BiosFile, folder: Path) -> list[Path]:
    """The files there for ``file``; one smaller than min_size is not one of them."""
    base = ROMS if file.in_roms else folder
    paths = sorted(base.glob(file.relative)) if file.is_glob else [base / file.relative]
    return [path for path in paths if _big_enough(path, file.min_size)]


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


## Before a game starts --------------------------------------------------------


def _system_content(system: str) -> Mapping[str, Any] | None:
    """The settings of one system, from its YAML of the highest layer."""
    # pylint: disable-next=import-outside-toplevel  # yaml, only when needed
    import yaml

    for layer in reversed(CONFIG_LAYERS):
        found = next((layer / "systems").glob(f"**/{system}.yaml"), None)
        if found is None:
            continue
        try:
            data = yaml.safe_load(found.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            _logger.error("Could not read %s: %s", found, error)
            return None
        content = data.get(system) if isinstance(data, dict) else None
        return content if isinstance(content, dict) else None
    return None


def describe(requirement: Requirement, folder: Path = BIOS) -> str:
    """What to put where to meet a requirement, for a message."""
    files = requirement.files
    if len(files) == 1 and files[0].is_glob:
        pattern = files[0].location(folder)
        return f"a dump (any {pattern.name}) in {pattern.parent}"
    names = [f"{file.path} ({file.note})" if file.note else file.path
             for file in files if not file.in_roms]
    elsewhere = [str(file.location(folder)) for file in files if file.in_roms]
    if not names:
        return " or ".join(elsewhere)
    if len(names) == 1:
        text = f"{names[0]} in {folder}"
    else:
        shown = ", ".join(names[:3]) + (f" (or {len(names) - 3} more)" if len(names) > 3 else "")
        text = f"one of {shown} in {folder}"
    return text + (f" (or {' / '.join(elsewhere)})" if elsewhere else "")


def require(system: str, emulator: str, core: str = "") -> None:
    """Check the BIOS ``emulator`` (and ``core``) needs to run a game of ``system``.

    A file that is there but is not a known dump is only logged: many
    alternative dumps work. An optional file is left out of this check on
    purpose: it is reported by the doctor and by EmulationStation's missing
    BIOS check, but a game must still start without it.

    Raises:
        RetroboxException: When a BIOS it can't run without is missing (its
            message, which EmulationStation shows, says what to put where).
    """
    content = _system_content(system)
    if content is None:
        return
    try:
        requirements = [r for r in parse(system, content) if r.required_by(emulator, core)]
    except BiosError as error:
        _logger.error("Ignoring the BIOS of %s: %s", system, error)
        return
    missing = []
    for result in check(requirements):
        if result.state is State.MISSING:
            missing.append(result.requirement)
        elif result.state is State.WRONG:
            _logger.warning("%s: %s is not a known dump of the %s", system,
                            ", ".join(path.name for path in result.files),
                            result.requirement.name)
    if missing:
        chosen = emulator if core in ("", emulator) else f"{emulator}/{core}"
        lines = [f"{requirement.name} missing: put {describe(requirement)}"
                 for requirement in missing]
        raise RetroboxException(f"{chosen} can't run without its BIOS.\n" + "\n".join(lines))


## EmulationStation's missing BIOS list -----------------------------------------


def chosen_emulator(system: str, content: Mapping[str, Any],
                    settings: Mapping[str, str]) -> tuple[str, str]:
    """The emulator and core ``system`` runs with: the one chosen in EmulationStation
    (``<system>.emulator`` / ``.core`` of es_settings.cfg), else its default."""
    emulator = settings.get(f"{system}.emulator", "")
    if not emulator or emulator == "auto":
        return default_emulator(content)
    return emulator, settings.get(f"{system}.core", "")


def _shown(file: BiosFile, folder: Path) -> str:
    """A file as the list shows it: relative to the BIOS folder, else its full path."""
    return str(file.location(folder)) if file.in_roms else file.path


def _es_line(result: Result, folder: Path) -> str:
    """One line of the list: ``STATUS MD5 what``, as batocera-systems prints it."""
    requirement = result.requirement
    files = requirement.files
    md5 = files[0].md5[0] if len(files) == 1 and files[0].md5 else "-"
    if len(files) == 1:
        what = _shown(files[0], folder)
    else:
        names = [_shown(file, folder) for file in files]
        parents = {PurePosixPath(file.path).parent for file in files if not file.in_roms}
        if len(names) <= 3:
            shown = " / ".join(names)
        elif len(parents) == 1 and not any(file.in_roms for file in files):
            shown = f"one of {len(names)} files in {parents.pop()}/"
        else:
            shown = f"{names[0]} / {names[1]} (or {len(names) - 2} more)"
        what = f"{requirement.name}: {shown}"
    status = "INVALID" if result.state is State.WRONG else "MISSING"
    return f"{status} {md5} {what}"


def es_report(systems: Iterable[tuple[str, Mapping[str, Any]]], settings: Mapping[str, str],
              folder: Path = BIOS) -> list[str]:
    """EmulationStation's missing BIOS list, in batocera-systems' format.

    For each system, the BIOS the emulator it runs with can't do without, the
    optional ones too (a game may run without them, but not as well), and the
    files that are there but are not known dumps: a ``> system`` line, then
    ``STATUS MD5 file`` lines (``MISSING`` or ``INVALID``). Systems with
    nothing to report are left out.
    """
    lines = []
    contents = dict(systems)
    for system, requirements in sorted(load_requirements(contents.items()).items()):
        emulator, core = chosen_emulator(system, contents[system], settings)
        reported = [r for r in requirements if r.optional or r.required_by(emulator, core)]
        problems = [r for r in check(reported, folder) if r.state is not State.FOUND]
        if problems:
            lines.append(f"> {system}")
            lines.extend(_es_line(result, folder) for result in problems)
    return lines


def main(argv: list[str] | None = None) -> int:
    """``retrobox-bios [--filter SYSTEM]``: print EmulationStation's missing BIOS list."""
    # pylint: disable=import-outside-toplevel  # only for the command line
    import argparse

    from retrobox.paths import ES_SETTINGS_CFG
    from retrobox.startup.frontend_conf.system_list_generator import load_systems
    from retrobox.utils.es_settings import read_es_settings

    parser = argparse.ArgumentParser(
        prog="retrobox-bios",
        description="List the BIOS files the systems' emulators miss, the way "
                    "batocera-systems does for EmulationStation's MISSING BIOS CHECK.")
    parser.add_argument("--filter", metavar="SYSTEM", help="only this system")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="retrobox-bios: %(message)s")
    systems = load_systems(system=args.filter)
    for line in es_report(systems, read_es_settings(ES_SETTINGS_CFG)):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
