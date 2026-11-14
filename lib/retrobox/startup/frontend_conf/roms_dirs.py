"""Create the ROM folder of every system, each with an ``_info.txt``.

On every start, each system that EmulationStation lists gets
``<roms_dir>/<system>`` if the folder is missing, with an ``_info.txt`` (as in
batocera) that says what goes in it: the file extensions the system accepts,
the emulators and cores that will run them and a few tips. It is written from
the system's YAML (see ``systems_config``), in English.

An ``_info.txt`` that already exists is never rewritten, whoever wrote it, and
a folder that exists is not changed in any other way. The text holds no paths
of this machine, so it stays true wherever the folder is moved.

Not given a folder: the systems with a ``path`` of their own in their YAML
(Retrobox's own entries, or one the user pointed elsewhere), the PC-games
stores (their sync manages them) and the ones without emulators (the groups).

``[core] create_rom_folders = false`` in retrobox.ini turns all of this off.
"""

from __future__ import annotations

import logging
import os
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from retrobox.paths import ROMS, get_ini_value
from retrobox.startup.frontend_conf.pcgames_paths import PCGAMES_SYSTEMS
from retrobox.startup.frontend_conf.system_list_generator import load_systems, system_roms_path

_logger = logging.getLogger(__name__)

INFO_FILE: Final = "_info.txt"
_SETTING_KEY: Final = "create_rom_folders"
_FALSE_VALUES: Final = frozenset({"false", "no", "off", "0"})
_WIDTH: Final = 79
_RULE: Final = "-" * _WIDTH


def enabled() -> bool:
    """Whether ``[core] create_rom_folders`` of retrobox.ini allows the folders (default: yes)."""
    return get_ini_value("core", _SETTING_KEY, "true").lower() not in _FALSE_VALUES


def _names(value: Any) -> list[str]:
    """A YAML value that is a list, a single value or nothing, as a list of strings."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item]
    return [str(value)]


def _extensions(value: Any) -> list[str]:
    """The extensions of a YAML value, lowercase and with their dot, without repeats."""
    seen: dict[str, None] = {}
    for extension in _names(value):
        extension = extension.strip().lower()
        if extension:
            seen[extension if extension.startswith(".") else f".{extension}"] = None
    return list(seen)


def _wrapped(text: str, indent: str = "") -> list[str]:
    """``text`` wrapped to the width of the file, every line after the first indented."""
    return textwrap.wrap(
        text,
        width=_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent + "  ",
        break_long_words=False,  # a path must stay in one piece
        break_on_hyphens=False,
    ) or [indent]


def _emulator_lines(emulators: Any, extensions: list[str]) -> list[str]:
    """The list of emulators and cores, then the extensions that some cores do not take."""
    if not isinstance(emulators, Mapping):
        return []
    lines: list[str] = []
    refused: list[tuple[str, list[str]]] = []
    for emulator, data in emulators.items():
        cores = data.get("cores") if isinstance(data, Mapping) else None
        names: list[str] = []
        for core, properties in (cores if isinstance(cores, Mapping) else {}).items():
            properties = properties if isinstance(properties, Mapping) else {}
            names.append(f"{core} *" if properties.get("default") is True else str(core))
            unsupported = [
                ext for ext in _extensions(properties.get("incompatible_extensions"))
                if ext in extensions
            ]
            if unsupported:
                refused.append((f"{emulator}/{core}", unsupported))
        lines += _wrapped(f"- {emulator}: {', '.join(names)}" if names else f"- {emulator}")
    if refused:
        lines += ["", "These cores do not accept some of the extensions above:"]
        for core, unsupported in refused:
            lines += _wrapped(f"- {core}: {' '.join(unsupported)}")
    return lines


def info_text(name: str, content: Mapping[str, Any]) -> str:
    """The ``_info.txt`` of a system.

    Args:
        name: The system's name (its folder's too).
        content: The system's settings, as its YAML has them.

    Returns:
        The text, ending in a line break.
    """
    title = str(content.get("fullname") or name)
    extensions = _extensions(content.get("extension"))
    details = [name]
    if manufacturer := str(content.get("manufacturer") or "").strip().lstrip("_"):
        details.append(manufacturer)
    release = str(content.get("release") or "").strip()
    if release.isdigit():
        details.append(release)
    if (hardware := str(content.get("hardware") or "").strip()) not in ("", "None"):
        details.append(hardware)

    lines = [
        f"## SYSTEM {title.upper()} ##",
        "",
        _RULE,
        f"System: {', '.join(details)}",
        "",
        *(
            _wrapped(f'ROM files extensions accepted: "{", ".join(extensions)}"')
            if extensions else ["ROM files extensions accepted: any"]
        ),
        "",
        _RULE,
        "Emulators and cores (* = default):",
        *(_emulator_lines(content.get("emulators"), extensions) or ["- none"]),
        "",
        _RULE,
        "Notes:",
        *_wrapped("- Put the games of this system in this folder. Subfolders are fine."),
        *_wrapped(
            "- The emulator and the core can be chosen for the whole system or for a single "
            "game from the options of EmulationStation."
        ),
        *_wrapped("- BIOS files, if the emulators need any, go in the bios folder of Retrobox."),
    ]
    if ".m3u" in extensions:
        lines += _wrapped(
            "- Games of several discs: put the discs in one folder and add an .m3u playlist "
            "that lists them, one file per line, then play the .m3u."
        )
    return "\n".join(lines) + "\n"


def _write_info(folder: Path, text: str) -> bool:
    """Write the ``_info.txt`` of a folder, unless it already has one.

    Returns:
        Whether the file was written.

    Raises:
        OSError: If it cannot be written.
    """
    target = folder / INFO_FILE
    if target.exists() or target.is_symlink():
        return False
    temporary = target.with_name(f".{INFO_FILE}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return True


def _wants_folder(name: str, content: Mapping[str, Any]) -> bool:
    """Whether a system gets a folder under the ROMs folder (see the module docstring)."""
    return bool(
        name not in PCGAMES_SYSTEMS
        and not content.get("path")
        and content.get("emulators")
    )


def create_roms_dirs(base_path: Path | None = None) -> int:
    """Create the missing ROM folders, each with an ``_info.txt`` if it has none.

    Nothing is created if the ROMs folder itself is missing: it may be a drive
    that is not mounted, and the folders would end up on the wrong disk.
    Problems with a folder (no permission, a file with its name) are logged and
    the others go on, so that Retrobox always starts.

    Args:
        base_path: Directory of the system YAML files; None (default) merges
            systems_config/ across the configuration layers.

    Returns:
        How many folders were created.
    """
    if not enabled():
        _logger.info("[core] %s is off: no ROM folders created", _SETTING_KEY)
        return 0
    if not ROMS.is_dir():
        _logger.warning("ROMs folder %s does not exist: no system folders created", ROMS)
        return 0
    try:
        systems = load_systems(base_path)
    except (FileNotFoundError, NotADirectoryError) as err:
        _logger.warning("No ROM folders created: %s", err)
        return 0

    created = failed = 0
    for name, content in systems:
        if not _wants_folder(name, content):
            continue
        folder = system_roms_path(name, content)
        try:
            if not folder.is_dir():
                folder.mkdir(parents=True)
                created += 1
            _write_info(folder, info_text(name, content))
        except OSError as err:
            failed += 1
            _logger.warning("Cannot prepare the ROM folder %s: %s", folder, err)
    if created:
        _logger.info("Created %d ROM folder(s) in %s", created, ROMS)
    if failed:
        _logger.warning("%d ROM folder(s) could not be prepared", failed)
    return created
