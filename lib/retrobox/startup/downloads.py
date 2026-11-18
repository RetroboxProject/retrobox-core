"""
Content Retrobox downloads before EmulationStation starts.

* ``theme``: the default theme, es-theme-iconic, into THEMES_DIR. Installed
  whenever EmulationStation has no theme at all (retrobox-core ships none).
* ``bezels``: the RetroBat bezels, the default decorations, into
  _DECORATIONS_DEF_DIR.
* ``shaders``: Retrobox's shaders and their sets (``configs/``), into
  _SHADERS_DIR.

Bezels and shaders are installed once, the first time Retrobox starts with
them on offer (the bezels only if their directory holds no files yet):
deleting them later doesn't bring them back. ``retrobox --download theme``
(``bezels``, ``shaders``) downloads them again, updating them or reinstalling
them if they were removed.

Each package is the latest commit of a GitHub repository, streamed as a
tar.gz archive and unpacked on the fly (no archive is kept on disk, which
matters for the bezels). Everything is unpacked into a hidden staging
directory next to the target, and an installed copy is only touched once
the new one is complete and valid: a failed or cancelled download leaves it
untouched. The theme and the bezels replace their directory as a whole (it
belongs to Retrobox); the shaders are merged into theirs, which may also
hold the user's own shaders. Nothing here stops the frontend from starting.

Run as ``python3 -m retrobox.startup.downloads PACKAGE...`` it downloads the
given packages, printing its progress: this is what the overlay's task screen
(``retrobox-overlay --task --download``) runs and shows, and what
``retrobox --download`` runs. With no package it lists them.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, BinaryIO, Final

from retrobox.configgen.utils.logger import OK, setup_logging
from retrobox.paths import (
    _DECORATIONS_DEF_DIR,
    _SHADERS_DIR,
    FRONTEND_DIR,
    STATE_DIR,
    THEMES_DIR,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_logger = logging.getLogger(__name__)

_TIMEOUT_S: Final = 60
_CHUNK: Final = 1 << 16
_PROGRESS_EVERY_S: Final = 0.5
_MIB: Final = 1 << 20
# Keys of the "once" packages already offered, one per line (see pending).
_OFFERED: Final = STATE_DIR / "downloads-offered"
# Its predecessor (v0.0.29): present once the bezels had been offered.
_LEGACY_FIRST_START: Final = STATE_DIR / "first-start.done"


@dataclass(frozen=True, slots=True)
class Package:
    """Something Retrobox downloads from GitHub."""

    name: str  # shown to the user
    url: str  # .tar.gz of a branch
    target: Path  # directory it is installed as
    marker: str = ""  # file that must be in a valid copy (relative path)
    once: bool = False  # offered once, else whenever the content is missing
    merge: bool = False  # merged into the target instead of replacing it


PACKAGES: Final[dict[str, Package]] = {
    "theme": Package(
        name="es-theme-iconic",
        url="https://github.com/manu-creative-411/es-theme-iconic/archive/refs/heads/main.tar.gz",
        target=THEMES_DIR / "es-theme-iconic",
        marker="theme.xml",
    ),
    "bezels": Package(
        name="RetroBat bezels",
        url="https://github.com/RetroBat-Official/retrobat-bezels/archive/refs/heads/master.tar.gz",
        target=_DECORATIONS_DEF_DIR,
        once=True,
    ),
    "shaders": Package(
        name="Retrobox shaders",
        url="https://github.com/RetroboxProject/retrobox-shaders/archive/refs/heads/main.tar.gz",
        target=_SHADERS_DIR,
        marker="configs/rendering-defaults.yml",
        once=True,
        merge=True,
    ),
}

_THEME_DIRS: Final = (FRONTEND_DIR / "themes", THEMES_DIR)


# ------------------------------------------------------------------ when
def has_theme() -> bool:
    """Whether EmulationStation has any theme (system-wide or the user's)."""
    for directory in _THEME_DIRS:
        try:
            if any(
                not entry.name.startswith(".") and (entry / "theme.xml").is_file()
                for entry in directory.iterdir()
            ):
                return True
        except OSError:
            continue
    return False


def _has_files(directory: Path) -> bool:
    """Whether ``directory`` holds any file (empty subdirectories don't count:
    the startup creates some of them, e.g. the shaders' ``configs``)."""
    try:
        return any(path.is_file() for path in directory.rglob("*"))
    except OSError:
        return False


def _offered() -> set[str]:
    """The "once" packages already offered."""
    try:
        offered = set(_OFFERED.read_text(encoding="utf-8").split())
    except OSError:
        offered = set()
    if _LEGACY_FIRST_START.exists():
        offered.add("bezels")
    return offered


def _mark_offered(keys: Iterable[str]) -> None:
    offered = _offered() | set(keys)
    try:
        _OFFERED.parent.mkdir(parents=True, exist_ok=True)
        _OFFERED.write_text("".join(f"{key}\n" for key in sorted(offered)), encoding="utf-8")
        _LEGACY_FIRST_START.unlink(missing_ok=True)
    except OSError as exc:
        _logger.warning("Couldn't write %s: %s", _OFFERED, exc)


def pending(updates: Iterable[str] = ()) -> list[str]:
    """The packages to download before this start (keys of PACKAGES).

    Every "once" package is recorded as offered right away, whatever happens
    to its download (it can be cancelled): only ``retrobox --download``
    brings it back.

    Args:
        updates: Packages to download again anyway.
    """
    updates = set(updates)
    offered = _offered()
    keys = []
    for key, package in PACKAGES.items():
        if key in updates:
            keys.append(key)
        elif package.once:
            # a merge never overwrites anything of the user's; a replacement
            # only goes ahead over a folder without files
            if key not in offered and (package.merge or not _has_files(package.target)):
                keys.append(key)
        elif key == "theme" and not has_theme():
            keys.append(key)
    _mark_offered(key for key, package in PACKAGES.items() if package.once)
    return keys


# -------------------------------------------------------------- download
class _Progress:  # pylint: disable=too-few-public-methods
    """A file-like wrapper over the HTTP response that prints how far it got."""

    def __init__(self, response: BinaryIO, total: int, name: str) -> None:
        self._response = response
        self._total = total
        self._name = name
        self._done = 0
        self._shown = 0.0

    def read(self, size: int = -1) -> bytes:
        """Read from the response, printing the progress now and then."""
        data = self._response.read(size if size > 0 else _CHUNK)
        self._done += len(data)
        now = time.monotonic()
        if now - self._shown >= _PROGRESS_EVERY_S:
            self._shown = now
            self._print()
        return data

    def finish(self) -> None:
        """Print the final figure and end the progress line."""
        self._print(end="\n")

    def _print(self, end: str = "") -> None:
        line = f"{self._name}: {self._done / _MIB:.1f}"
        if self._total > 0:
            percent = min(100, self._done * 100 // self._total)
            line += f" / {self._total / _MIB:.1f} MiB ({percent}%)"
        else:
            line += " MiB"
        # \r: the task screen (like a terminal) rewrites the same line
        print(f"\r{line}", end=end, flush=True)


def _safe_members(archive: tarfile.TarFile) -> Iterable[tarfile.TarInfo]:
    """Regular files and directories that stay inside the destination."""
    for member in archive:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise tarfile.TarError(f"unsafe path in the archive: {member.name}")
        if member.isfile() or member.isdir():
            yield member


def _unpack(stream: _Progress, destination: Path) -> None:
    """Unpack a tar.gz stream into ``destination``, as it arrives."""
    # pylint: disable-next=consider-using-with
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:  # type: ignore[call-overload]
        extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        for member in _safe_members(archive):
            archive.extract(member, destination, **extra)


def _root_of(extracted: Path, package: Package) -> Path:
    """The package's tree inside the archive (GitHub wraps it in one directory)."""
    entries = list(extracted.iterdir())
    root = entries[0] if len(entries) == 1 and entries[0].is_dir() else extracted
    if package.marker and not (root / package.marker).is_file():
        raise ValueError(f"no {package.marker} in the archive")
    if not _has_files(root):
        raise ValueError("the archive is empty")
    return root


def _merge(source: Path, target: Path) -> None:
    """Move every file of ``source`` into ``target``, replacing same-named ones.

    Files only ``target`` has (the user's own) are kept. Each move is a
    rename within one filesystem.
    """
    for path in sorted(source.rglob("*")):
        destination = target / path.relative_to(source)
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            path.replace(destination)


def install(package: Package) -> bool:
    """Download ``package`` and install it, replacing (or merging into) any
    previous copy.

    Returns:
        True if it was installed.
    """
    target = package.target
    if target.is_symlink():
        _logger.error("%s is a symlink; not replacing it", target)
        return False

    _logger.info("Downloading %s", package.name)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".download-", dir=target.parent) as tmp:
            staging = Path(tmp)
            extracted = staging / "extracted"
            extracted.mkdir()
            with urllib.request.urlopen(package.url, timeout=_TIMEOUT_S) as response:
                total = int(response.headers.get("Content-Length") or 0)
                progress = _Progress(response, total, package.name)
                try:
                    _unpack(progress, extracted)
                finally:
                    progress.finish()
            root = _root_of(extracted, package)

            if package.merge and target.is_dir():
                _merge(root, target)
            else:
                # the previous copy goes into the staging directory, deleted on the way out
                if target.exists():
                    target.rename(staging / "previous")
                root.rename(target)
    except (OSError, tarfile.TarError, ValueError) as exc:
        _logger.error("Couldn't install %s: %s", package.name, exc)
        return False

    _logger.log(OK, "%s installed in %s", package.name, target)
    return True


def install_all(keys: Sequence[str]) -> bool:
    """Install the packages ``keys``; True if all of them were installed."""
    results = [install(PACKAGES[key]) for key in keys]
    return all(results)


def labels(keys: Sequence[str]) -> str:
    """The packages ``keys`` as shown to the user."""
    return ", ".join(PACKAGES[key].name for key in keys)


# ------------------------------------------------------------------ CLI
def _handle_sigterm(signum: int, _frame: object) -> None:
    """Exit through the context managers, so that staging dirs are removed."""
    raise SystemExit(128 + signum)


def main(argv: Sequence[str] | None = None) -> int:
    """Download the packages named on the command line (none: list them); 0 if all went fine."""
    parser = argparse.ArgumentParser(
        prog="python3 -m retrobox.startup.downloads",
        description="Download Retrobox's default content.",
    )
    parser.add_argument("packages", nargs="*", choices=sorted(PACKAGES))
    args = parser.parse_args(argv)
    if not args.packages:
        print("Available downloads:")
        for key, package in PACKAGES.items():
            print(f"  {key:<14} {package.name}")
        return 0
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGHUP, _handle_sigterm)
    with setup_logging():
        return 0 if install_all(args.packages) else 1


if __name__ == "__main__":
    sys.exit(main())
