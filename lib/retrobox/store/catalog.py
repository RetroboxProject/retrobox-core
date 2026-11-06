"""The package catalog: pacman's sync database of a repository.

A repository is a directory (HTTPS or ``file://``) with ``<name>.db``, a tar
archive with one ``<package>-<version>/desc`` file per package, and the package
files themselves. Only what the store needs of the format is read here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .archive import open_tar_stream

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# the only architecture that holds plain data (music, bezels, ROMs...): the
# others are batocera's own binaries, which cannot run here
ANY_ARCH = "any"

_SECTION = re.compile(r"^%([A-Z0-9]+)%$")
_KILOBYTE = 1024


@dataclass(frozen=True)
class Package:  # pylint: disable=too-many-instance-attributes
    """One package of the catalog."""

    name: str
    version: str
    filename: str
    description: str = ""
    url: str = ""
    packager: str = ""
    arch: str = ANY_ARCH
    sha256: str = ""
    download_size: int = 0
    installed_size: int = 0
    groups: tuple[str, ...] = field(default_factory=tuple)
    licenses: tuple[str, ...] = field(default_factory=tuple)

    @property
    def download_size_kb(self) -> int:
        """The download size in KiB, the unit the store menu shows."""
        return self.download_size // _KILOBYTE

    @property
    def installed_size_kb(self) -> int:
        """The installed size in KiB."""
        return self.installed_size // _KILOBYTE


def _parse_sections(text: str) -> dict[str, list[str]]:
    """Split a ``desc`` file into its ``%SECTION%`` blocks."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if match := _SECTION.match(line):
            current = sections.setdefault(match.group(1), [])
        elif line and current is not None:
            current.append(line)
    return sections


def _first(sections: dict[str, list[str]], key: str, default: str = "") -> str:
    """The first line of a section."""
    values = sections.get(key)
    return values[0] if values else default


def _to_int(value: str) -> int:
    """An integer from a ``desc`` value, 0 if it is not one."""
    try:
        return int(value)
    except ValueError:
        return 0


def parse_desc(text: str) -> Package | None:
    """Read the ``desc`` file of a package.

    Args:
        text: The content of the file.

    Returns:
        The package, or None if it lacks a name, a version or a file name.
    """
    sections = _parse_sections(text)
    name = _first(sections, "NAME")
    version = _first(sections, "VERSION")
    filename = _first(sections, "FILENAME")
    if not (name and version and filename):
        return None
    return Package(
        name=name,
        version=version,
        filename=filename,
        # a description may span several lines
        description=" ".join(sections.get("DESC", [])),
        url=_first(sections, "URL"),
        packager=_first(sections, "PACKAGER"),
        arch=_first(sections, "ARCH", ANY_ARCH),
        sha256=_first(sections, "SHA256SUM").lower(),
        download_size=_to_int(_first(sections, "CSIZE")),
        installed_size=_to_int(_first(sections, "ISIZE")),
        groups=tuple(sections.get("GROUPS", [])),
        licenses=tuple(sections.get("LICENSE", [])),
    )


def load_catalog(database: Path) -> dict[str, Package]:
    """Read every package of a sync database.

    Args:
        database: The ``<repository>.db`` file.

    Returns:
        The usable packages (architecture ``any``) by name. If a name appears
        twice, the newest version is kept.
    """
    packages: dict[str, Package] = {}
    with open_tar_stream(database) as archive:
        for member in archive:
            if not (member.isfile() and member.name.endswith("/desc")):
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            package = parse_desc(stream.read().decode("utf-8", errors="replace"))
            if package is None:
                _logger.warning("ignoring the malformed entry %s", member.name)
            elif package.arch != ANY_ARCH:
                _logger.debug("ignoring %s: it is for %s", package.name, package.arch)
            elif package.name not in packages or compare_versions(
                package.version, packages[package.name].version
            ) > 0:
                packages[package.name] = package
    return packages


def _split_version(version: str) -> tuple[str, str, str]:
    """Split ``[epoch:]version[-release]`` into its three parts."""
    epoch, separator, rest = version.partition(":")
    if not separator:
        epoch, rest = "0", version
    main, separator, release = rest.rpartition("-")
    if not separator:
        main, release = rest, ""
    return epoch, main, release


def _compare_segments(first: str, second: str) -> int:
    """Compare two version strings segment by segment (pacman's rpmvercmp)."""
    if first == second:
        return 0
    tokens_a = re.findall(r"[0-9]+|[A-Za-z]+", first)
    tokens_b = re.findall(r"[0-9]+|[A-Za-z]+", second)
    for token_a, token_b in zip(tokens_a, tokens_b):
        if token_a.isdigit() != token_b.isdigit():
            # a number is newer than letters
            return 1 if token_a.isdigit() else -1
        if token_a.isdigit():
            number_a, number_b = int(token_a), int(token_b)
            if number_a != number_b:
                return 1 if number_a > number_b else -1
        elif token_a != token_b:
            return 1 if token_a > token_b else -1
    if len(tokens_a) == len(tokens_b):
        return 0
    # the longer one wins, unless what is left is letters (1.0a < 1.0)
    longer, sign = (tokens_a, 1) if len(tokens_a) > len(tokens_b) else (tokens_b, -1)
    leftover = longer[min(len(tokens_a), len(tokens_b))]
    return -sign if leftover.isalpha() else sign


def compare_versions(first: str, second: str) -> int:
    """Compare two package versions like pacman's ``vercmp``.

    Args:
        first: A version, ``[epoch:]version[-release]``.
        second: Another version.

    Returns:
        1 if the first is newer, -1 if it is older, 0 if they are the same.
    """
    parts_a = _split_version(first)
    parts_b = _split_version(second)
    for part_a, part_b in zip(parts_a, parts_b):
        if result := _compare_segments(part_a, part_b):
            return result
    return 0
