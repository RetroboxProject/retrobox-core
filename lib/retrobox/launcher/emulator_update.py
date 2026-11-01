"""Install an emulator again without risking the working copy.

Run by the setup screen as its command (``python3 -m
retrobox.launcher.emulator_update <emulator>``) when the hotkey was held while
a game started. The emulator's own installer runs with
``RETROBOX_EMULATORS_DIR`` pointing at a staging folder
(``<emulators>/.update-<installer>/``), so it builds or downloads the new
version there and never sees the installed one. Only when it succeeds and the
new binary exists is the installed folder replaced:

1. user data is carried over from the installed folder into the new one:
   every top-level entry the new install doesn't have (saves, NVRAM...), and
   the emulator's ``keep`` paths (``config`` and the like), which win over
   what the installer shipped;
2. the installed folder is renamed aside, the new one moved into its place,
   and the old one deleted. If the move fails, the old folder is put back.

On any failure the staging folder is deleted and the installed emulator is
left exactly as it was. The output goes to the screen's terminal.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from retrobox.paths import BIN_DIR, EMULATORS

from .emulator_setup import binary_of, installable, unit_of

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import FrameType

    from .emulator_setup import Installable

# caches under <emulators>/ that installers reuse between runs: shared with the
# staging folder instead of being downloaded again (vita3k's Qt, ~300 MB)
_SHARED_CACHES: Final = ("_qt6",)

_STAGING_PREFIX: Final = ".update-"


class _Interrupted(Exception):
    """The screen was closed (SIGTERM/SIGHUP) while the installer ran."""


def _say(message: str) -> None:
    print(f"[retrobox] {message}", flush=True)


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _copy(source: Path, destination: Path) -> None:
    _remove(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)


def _carry_user_data(installed: Path, staged: Path, keep: Iterable[str]) -> None:
    """Copy the user data of the installed folder into the staged one."""
    if not installed.is_dir():
        return
    kept = set()
    for name in keep:
        source = installed / name
        if source.exists() or source.is_symlink():
            _copy(source, staged / name)
            kept.add(Path(name).parts[0])
    for child in installed.iterdir():
        if child.name not in kept and not (staged / child.name).exists():
            _copy(child, staged / child.name)


def _swap(installed: Path, staged: Path) -> None:
    """Put ``staged`` where ``installed`` is, keeping the old one until it worked."""
    backup = installed.with_name(f".{installed.name}.old")
    _remove(backup)
    installed.parent.mkdir(parents=True, exist_ok=True)
    had_installed = installed.exists()
    if had_installed:
        installed.rename(backup)
    try:
        shutil.move(staged, installed)  # a rename when on the same filesystem
    except OSError:
        _remove(installed)
        if had_installed:
            backup.rename(installed)
        raise
    _remove(backup)


def _on_signal(signum: int, _frame: FrameType | None) -> None:
    raise _Interrupted(signum)


def _run_installer(installer: str, staging: Path) -> int:
    for name in _SHARED_CACHES:
        if (EMULATORS / name).is_dir():
            (staging / name).symlink_to(EMULATORS / name)
    environment = {**os.environ, "RETROBOX_EMULATORS_DIR": str(staging)}
    command = [str(BIN_DIR / "retrobox"), "--setup-emulator", installer]
    try:
        with subprocess.Popen(command, env=environment) as process:
            try:
                return process.wait()
            except _Interrupted:
                process.terminate()
                process.wait()
                raise
    finally:
        # a cache the installer created this time is kept for the next one
        for name in _SHARED_CACHES:
            created = staging / name
            if created.is_dir() and not created.is_symlink() and not (EMULATORS / name).exists():
                shutil.move(created, EMULATORS / name)


def _resolve(emulator: str) -> tuple[Installable, Path] | None:
    """The entry of ``emulator`` and its binary relative to the emulators directory."""
    entry = installable(emulator)
    binary = binary_of(entry) if entry else None
    if entry is None or binary is None:
        _say(f"'{emulator}' has no installer in Retrobox.")
        return None
    try:
        return entry, binary.relative_to(EMULATORS)
    except ValueError:
        _say(f"{binary} is outside {EMULATORS}: cannot install it in a separate folder.")
        return None


def update(emulator: str) -> int:
    """Install ``emulator`` again in a staging folder and swap it in on success.

    Returns:
        0 when the new version is in place; 1 otherwise (the installed one is
        untouched).
    """
    resolved = _resolve(emulator)
    if resolved is None:
        return 1
    entry, relative_binary = resolved
    unit = unit_of(entry, relative_binary)
    installed = EMULATORS / unit
    staging = EMULATORS / f"{_STAGING_PREFIX}{entry.installer}"

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGHUP, _on_signal)
    _remove(staging)  # leftovers of an interrupted attempt
    staging.mkdir(parents=True)
    try:
        _say(f"Installing {entry.label} in {staging}; the installed version is not "
             "touched until the new one works.")
        status = _run_installer(entry.installer, staging)
        if status:
            _say(f"The installer failed (status {status}): {entry.label} was not changed.")
            return 1
        if not (staging / relative_binary).exists():
            _say(f"The installer finished but did not produce {relative_binary}: "
                 f"{entry.label} was not changed.")
            return 1

        # from here on the swap must not be cut halfway
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(signum, signal.SIG_IGN)
        _say("Keeping the configuration and data of the installed version...")
        _carry_user_data(installed, staging / unit, entry.keep)
        _say(f"Replacing {installed}...")
        _swap(installed, staging / unit)
    except _Interrupted:
        _say(f"Interrupted: {entry.label} was not changed.")
        return 1
    except OSError as error:
        _say(f"Could not put the new version in place ({error}): {entry.label} was not changed.")
        return 1
    finally:
        _remove(staging)
    _say(f"{entry.label} was installed again.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """``python3 -m retrobox.launcher.emulator_update <emulator>``."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: python3 -m retrobox.launcher.emulator_update <emulator>", file=sys.stderr)
        return 2
    return update(arguments[0])


if __name__ == "__main__":
    sys.exit(main())
