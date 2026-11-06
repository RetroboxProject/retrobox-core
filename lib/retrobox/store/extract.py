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
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import IO, TYPE_CHECKING, Final

from retrobox.paths import (
    BIOS,
    CHEATS,
    EMULATORS_CONFIG,
    MUSIC_DIR,
    ROMS,
    SAVES,
    SCREENSHOTS,
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

    roots: Mapping[str, Path]  # "folder" or "folder/subfolder" of userdata -> directory

    @classmethod
    def default(cls) -> Layout:
        """The directories of the current Retrobox installation."""
        return cls(
            {
                "bios": BIOS,
                "cheats": CHEATS,
                "decorations": _DECORATIONS_DIR,
                "music": MUSIC_DIR,
                "roms": ROMS,
                "saves": SAVES,
                "screenshots": SCREENSHOTS,
                "shaders": _SHADERS_DIR,
                "themes": THEMES_DIR,
                # batocera's /userdata/system/configs/<emu> is <config dir>/emulators/<emu>
                "system/configs": EMULATORS_CONFIG,
            }
        )

    def root_of(self, parts: tuple[str, ...]) -> Path:
        """The directory a (valid) path of ``userdata/`` goes into."""
        for length in range(min(len(parts), 2), 0, -1):
            if (root := self.roots.get("/".join(parts[:length]))) is not None:
                return root
        raise KeyError(parts)

    def target(self, parts: tuple[str, ...]) -> Path | None:
        """The file for a path of ``userdata/``, or None if it has no place here.

        Args:
            parts: The path inside ``userdata/``, split in components.
        """
        # the longest prefix wins ("system/configs" before a plain "system")
        for length in range(min(len(parts), 2), 0, -1):
            if (root := self.roots.get("/".join(parts[:length]))) is not None:
                rest = parts[length:]
                break
        else:
            return None
        if not rest or any(part in ("", ".", "..") or "\x00" in part for part in rest):
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


def _make_progress(
    expected_bytes: int, report: Callable[[str, int], None]
) -> Callable[[int], None]:
    """A counter of the bytes written that reports the percentage now and then."""
    done = 0
    last = 0.0

    def add(written: int) -> None:
        nonlocal done, last
        done += written
        now = time.monotonic()
        if now - last >= _REPORT_INTERVAL:
            last = now
            report("Installing", min(99, done * 100 // expected_bytes) if expected_bytes else 0)

    return add


def _read_batoexec(
    archive: tarfile.TarFile, member: tarfile.TarInfo, parts: tuple[str, ...], result: Extraction
) -> None:
    """Keep the text of a ``.batoexec`` file of the package."""
    if len(parts) != len(_BATOEXEC_DIR) + 1 or member.size > _BATOEXEC_MAX_BYTES:
        return
    if (stream := archive.extractfile(member)) is not None:
        result.batoexec.append(stream.read().decode("utf-8", errors="replace"))


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
        expected_bytes: The installed size, for the progress and the free space.
        result: Filled in as files are written, so the caller can undo a failure.
        report: Called now and then with a text and the percentage done.

    Raises:
        OSError: A file cannot be written, or a directory has no room for the package.
    """
    count_written = _make_progress(expected_bytes, report)
    checked: set[Path] = set()
    with open_tar_stream(archive_path) as archive:
        for member in archive:
            parts = _member_parts(member.name)
            if parts is None:
                continue
            if parts[: len(_BATOEXEC_DIR)] == _BATOEXEC_DIR and member.isfile():
                _read_batoexec(archive, member, parts, result)
                continue

            target = layout.target(parts)
            if target is None or not (member.isdir() or member.isfile()):
                # no place here, or links, devices and the like
                result.skipped += 1
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if (stream := archive.extractfile(member)) is None:
                continue

            root = layout.root_of(parts)
            if root not in checked:
                # each root may be on its own disk (the ROMs directory often is)
                checked.add(root)
                if not free_space_ok(root, expected_bytes):
                    raise OSError(f"not enough disk space in {root}")
            count_written(_write_file(stream, target, bool(member.mode & 0o100)))
            result.files.append(str(target))

    if result.skipped:
        _logger.debug("%d entries of the package have no place here", result.skipped)


def free_space_ok(directory: Path, needed: int) -> bool:
    """Whether the filesystem of ``directory`` has room for ``needed`` bytes (+10%)."""
    probe = directory
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free >= needed * 11 // 10
