"""Unpacking a package into the Retrobox directories.

Packages are built for batocera, where everything lives under ``/userdata``;
inside the archive that is the ``userdata/`` folder. Its subfolders are mapped
to the directories of Retrobox (see ``Layout``); what has no place here is
skipped. The archive is untrusted: nothing may be written outside those
directories, so links and special files are never created.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import IO, TYPE_CHECKING, Final

from retrobox.paths import (
    BIOS,
    MUSIC_DIR,
    ROMS,
    SAVES,
    THEMES_DIR,
    _DECORATIONS_DIR,
    _SHADERS_DIR,
)

from .archive import open_tar_stream

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_logger = logging.getLogger(__name__)

_COPY_CHUNK: Final = 256 * 1024
_REPORT_INTERVAL: Final = 0.5
_BATOEXEC_DIR: Final = ("system", "pacman", "batoexec")
# a .batoexec file is a few lines: anything bigger is not one
_BATOEXEC_MAX_BYTES: Final = 1024 * 1024


@dataclass(frozen=True)
class Layout:
    """Where each folder of batocera's ``userdata`` goes."""

    roots: Mapping[str, Path]

    @classmethod
    def default(cls) -> Layout:
        """The directories of the current Retrobox installation."""
        return cls(
            {
                "bios": BIOS,
                "decorations": _DECORATIONS_DIR,
                "music": MUSIC_DIR,
                "roms": ROMS,
                "saves": SAVES,
                "shaders": _SHADERS_DIR,
                "themes": THEMES_DIR,
            }
        )

    def target(self, parts: tuple[str, ...]) -> Path | None:
        """The file for a path of ``userdata/``, or None if it has no place here.

        Args:
            parts: The path inside ``userdata/``, split in components.
        """
        if not parts or (root := self.roots.get(parts[0])) is None:
            return None
        rest = parts[1:]
        if any(part in ("", ".", "..") or "\x00" in part for part in rest):
            return None
        target = root.joinpath(*rest)
        # a link that is already there must not lead out of the root
        resolved_root = root.resolve()
        parent = target.parent.resolve()
        if parent != resolved_root and resolved_root not in parent.parents:
            return None
        return target


@dataclass
class Extraction:
    """What unpacking a package did."""

    files: list[str] = field(default_factory=list)
    batoexec: list[str] = field(default_factory=list)
    skipped: int = 0


def _member_parts(name: str) -> tuple[str, ...] | None:
    """The components of the path of a member inside ``userdata/``, or None to skip it."""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return None
    parts = tuple(part for part in path.parts if part != ".")
    if len(parts) < 2 or parts[0] != "userdata":
        # the metadata of the package (.PKGINFO, .MTREE...) and anything else
        return None
    return parts[1:]


def _write_file(source: IO[bytes], target: Path, executable: bool) -> int:
    """Write one file, replacing whatever is there (a link included)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.is_file():
        target.unlink()
    written = 0
    with target.open("wb") as output:
        while chunk := source.read(_COPY_CHUNK):
            output.write(chunk)
            written += len(chunk)
    os.chmod(target, 0o755 if executable else 0o644)
    return written


def extract_package(
    archive_path: Path,
    layout: Layout,
    expected_bytes: int,
    result: Extraction,
    report: Callable[[str, int], None],
) -> None:
    """Unpack a package.

    Args:
        archive_path: The package file.
        layout: Where the folders of ``userdata/`` go.
        expected_bytes: The installed size, for the progress.
        result: Filled in as files are written, so the caller can undo a failure.
        report: Called now and then with a text and the percentage done.
    """
    done = 0
    last_report = 0.0
    with open_tar_stream(archive_path) as archive:
        for member in archive:
            parts = _member_parts(member.name)
            if parts is None:
                continue
            if parts[: len(_BATOEXEC_DIR)] == _BATOEXEC_DIR and member.isfile():
                if len(parts) == len(_BATOEXEC_DIR) + 1 and member.size <= _BATOEXEC_MAX_BYTES:
                    stream = archive.extractfile(member)
                    if stream is not None:
                        result.batoexec.append(stream.read().decode("utf-8", errors="replace"))
                continue

            target = layout.target(parts)
            if target is None:
                result.skipped += 1
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                # links, devices and the like
                result.skipped += 1
                continue

            stream = archive.extractfile(member)
            if stream is None:
                continue
            done += _write_file(stream, target, bool(member.mode & 0o100))
            result.files.append(str(target))

            now = time.monotonic()
            if now - last_report >= _REPORT_INTERVAL:
                last_report = now
                percent = min(99, done * 100 // expected_bytes) if expected_bytes else 0
                report("Installing", percent)

    if result.skipped:
        _logger.debug("%d entries of the package have no place here", result.skipped)


def free_space_ok(directory: Path, needed: int) -> bool:
    """Whether the filesystem of ``directory`` has room for ``needed`` bytes (+10%)."""
    probe = directory
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free >= needed * 11 // 10
