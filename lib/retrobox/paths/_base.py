"""
Base runtime paths module.

Zero knowledge of configgen, launcher, frontend (EmulationStation),
or gamepadly. Only generic path resolution (XDG, ROOTDIR) and filesystem
helpers. This is the only module in the package that other subsystems
of the project (outside of retrobox_paths) should consider truly
"independent".
"""

from __future__ import annotations

import configparser
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Final, overload

if TYPE_CHECKING:
    from _typeshed import (
        OpenBinaryModeUpdating,
        OpenBinaryModeWriting,
        OpenTextModeUpdating,
        OpenTextModeWriting,
    )
    from collections.abc import Generator, Iterable
    from io import BufferedRandom, BufferedWriter, TextIOWrapper


def check_env_dirs(variable: str, default_dir: Path) -> Path:
    """
    Safely assign directory values with environment variable overrides.

    Checks if the environment variable `variable` is set and points to
    a valid, readable directory. If so, returns that path; otherwise,
    returns `default_dir`.

    Args:
        variable: The environment variable name to check.
        default_dir: The fallback directory path if the override is invalid.

    Returns:
        The resolved directory path.
    """
    override = Path(os.environ.get(variable, str(default_dir)))
    if override.exists() and override.is_dir() and os.access(override, os.R_OK):
        return override
    return default_dir


# ---------------------------------------------------------------------------
# retrobox.ini: layered, read-only configuration
#
# Retrobox never writes retrobox.ini. Every setting has a default in code;
# the file only holds what somebody wants to change. It is read from two
# places, the later one overriding the earlier one key by key:
#
#   1. /etc/retrobox/retrobox.ini        + retrobox.ini.d/*.ini   (system-wide)
#   2. ~/.config/retrobox/retrobox.ini   + retrobox.ini.d/*.ini   (per user)
#
# Inside each place the main file is read first, then the drop-ins in
# alphabetical order, so `retrobox.ini.d/50-mypaths.ini` beats retrobox.ini.
#
# Sections:
#   [core]    -> autocorrect_paths, ignore_systems, ...
#   [paths]   -> roms_dir, saves_dir, bios_dir. If autocorrect_paths is true
#                (default) an unset or invalid path falls back to its default
#                directory, which is created. If false, nothing is created and
#                the value is used as written.
#   [environ] -> Literal dump to os.environ (API keys, STEAM_LIBRARY_DIR...).
#                No validation; key case is respected (they are real variable
#                names). Variables already set in the environment win.
#   [advanced] and any other section are available through get_ini_value().
#
# [core] and [paths] key names are matched case-insensitively (older files
# used UPPERCASE); the file itself is never rewritten.
# ---------------------------------------------------------------------------

# Default subdirectory (relative to DATA_DIR) of each [paths] key.
_PATH_DEFAULTS: Final[dict[str, str]] = {
    "roms_dir": "roms",
    "saves_dir": "saves",
    "bios_dir": "bios",
}

_CASE_INSENSITIVE_SECTIONS: Final[tuple[str, ...]] = ("core", "paths")
_TRUE_VALUES: Final[frozenset[str]] = frozenset({"true", "1", "yes", "on"})


class CaseSensitiveConfigParser(configparser.ConfigParser):
    """
    A ConfigParser subclass that preserves the case of option keys.

    By default, ConfigParser lowercases all option names. This subclass
    overrides `optionxform` to return the option string unchanged. This
    is also the standard way to fix Pylance/Pyright type errors when
    trying to assign `str` to `optionxform` (since it's typed as a method
    in typeshed, not a simple attribute).
    """

    def optionxform(self, optionstr: str) -> str:
        """Return the option string unchanged to preserve case."""
        return optionstr


def _ini_files(*layer_dirs: Path) -> list[Path]:
    """List the ini files of each layer, lowest priority first."""
    files: list[Path] = []
    for layer in layer_dirs:
        main = layer / "retrobox.ini"
        if main.is_file():
            files.append(main)
        dropin_dir = layer / "retrobox.ini.d"
        try:
            files.extend(sorted(p for p in dropin_dir.glob("*.ini") if p.is_file()))
        except OSError:
            pass
    return files


def _load_layered_ini(files: "Iterable[Path]") -> CaseSensitiveConfigParser:
    """Merge `files` (in order) into a single parser. Never touches the disk."""
    merged = CaseSensitiveConfigParser(interpolation=None)
    for path in files:
        parser = CaseSensitiveConfigParser(interpolation=None)
        try:
            parser.read(path, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError) as exc:
            # A broken drop-in must not take the whole program down.
            print(f"retrobox: ignoring unreadable config {path}: {str(exc).splitlines()[0]}", file=sys.stderr)
            continue
        for section in parser.sections():
            if not merged.has_section(section):
                merged.add_section(section)
            for key, value in parser.items(section):
                if section in _CASE_INSENSITIVE_SECTIONS:
                    # Drop any spelling of the key set by a lower layer.
                    for existing in [k for k in merged[section] if k.lower() == key.lower()]:
                        merged.remove_option(section, existing)
                    key = key.lower()
                merged.set(section, key, value)
    for section in ("core", "paths", "environ"):
        if not merged.has_section(section):
            merged.add_section(section)
    return merged


def _bootstrap_env(config: CaseSensitiveConfigParser) -> None:
    """
    Dump [environ] into os.environ. Must run BEFORE the Final constants of
    this package are computed, because they may be overridden from there.
    """
    for key, value in config.items("environ"):
        value = value.strip()
        # An empty value means "undefined": fall back to the consumer's
        # default instead of overwriting with "".
        if key and value:
            os.environ.setdefault(key, value)


def _autocorrect() -> bool:
    raw = _PATHS_CONFIG.get("core", "autocorrect_paths", fallback="true")
    return raw.strip().lower() in _TRUE_VALUES


def get_configured_path(key: str, default: Path) -> Path:
    """
    Resolve a [paths] entry of retrobox.ini.

    With autocorrect_paths=true (default): the configured value is used if it
    is a readable directory, otherwise `default` is used and created.
    With autocorrect_paths=false: the configured value is returned as
    written (even if missing); `default` only when nothing is configured.
    """
    value = os.path.expandvars(_PATHS_CONFIG.get("paths", key, fallback="").strip())
    value = os.path.expanduser(value)
    if _autocorrect():
        if value and Path(value).is_dir() and os.access(value, os.R_OK):
            return Path(value)
        try:
            default.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return default
    return Path(value) if value else default


def get_ignored_systems() -> frozenset[str]:
    """
    Read [core] ignore_systems: a comma-separated list of system names
    (the top-level key of each systems_config *.yaml, e.g. "gba", "psp")
    that are skipped when generating es_systems.cfg.
    """
    raw = _PATHS_CONFIG.get("core", "ignore_systems", fallback="")
    return frozenset(name.strip().lower() for name in raw.split(",") if name.strip())


def get_ini_value(section: str, key: str, default: str = "") -> str:
    """Read any value of the merged retrobox.ini (stripped)."""
    if section in _CASE_INSENSITIVE_SECTIONS:
        key = key.lower()
    return _PATHS_CONFIG.get(section, key, fallback=default).strip()


# ---------------------------------------------------------------------------
# Installation layout: system side vs user side
#
# RETROBOX_ROOTDIR is where the project's code and bundled data live
# (a git checkout, /opt/retrobox from the .deb, the prefix install.sh was
# given...). It is read-only: nothing is ever written there.
#
# The configuration is layered. Each layer mirrors the directory structure of
# share/ (systems_config/, emu_features/, hooks/...) and a file in a later
# layer replaces the same file of an earlier one:
#
#   1. $RETROBOX_ROOTDIR/share     shipped defaults (read-only)
#   2. /etc/retrobox                   administrator's overrides (optional)
#   3. ~/.config/retrobox              user's overrides (optional)
#
# What the user (or the program) writes lives in XDG directories, the same
# ones whichever way Retrobox was installed:
#
#   CONFIG_DIR  ~/.config/retrobox     retrobox.ini(.d), overrides of
#                                      share/, .env, emulators/<emu>/ (each
#                                      emulator's XDG_CONFIG_HOME), the
#                                      EmulationStation home, pad2key profiles
#   DATA_DIR    ~/.local/share/retrobox  roms, saves, bios, themes, bezels,
#                                      shaders, menu music, emulators (the
#                                      binaries), screenshots, recordings...
#   STATE_DIR   ~/.local/state/retrobox  logs, installer manifests
#
# (~/.config, ~/.local/share and ~/.local/state when the XDG variables are
# unset.) Each one can be moved with RETROBOX_CONFIGDIR / RETROBOX_DATADIR /
# RETROBOX_STATEDIR, and /etc/retrobox with RETROBOX_SYSCONFDIR. The big
# content directories (roms, saves, bios) can be moved on their own from the
# [paths] section of retrobox.ini.
#
# The resolved values are exported back to os.environ (see _env.py) so child
# processes (emulatorlauncher, shell scripts, hooks) see exactly the same
# directories, and `python3 -m retrobox.paths --shell` hands them to the bash
# installers: this module is the single source of truth.
# ---------------------------------------------------------------------------
# <root>/lib/retrobox/paths/_base.py -> <root>
_ROOTDIR_GUESS: Final[Path] = Path(__file__).resolve().parents[3]
RETROBOX_ROOTDIR: Final[Path] = check_env_dirs("RETROBOX_ROOTDIR", _ROOTDIR_GUESS)

# XDG Helpers
_USER_HOME: Final[Path] = Path.home()
_XDG_DATA: Final[Path] = Path.home() / ".local" / "share"
_XDG_CACHE: Final[Path] = Path.home() / ".cache"
_XDG_CONFIG: Final[Path] = Path.home() / ".config"
_XDG_STATE: Final[Path] = Path.home() / ".local" / "state"
_SYSTEM_LOCAL_BIN: Final[Path] = Path("/usr/local/bin")
_SYSTEM_LOCAL_SHARE: Final[Path] = Path("/usr/local/share")


def _resolve_dir(override: str, xdg_var: str, xdg_fallback: Path) -> Path:
    """Resolve one mutable directory: explicit override > $XDG_* > default."""
    value = os.environ.get(override, "").strip()
    if value:
        return Path(value)
    xdg = os.environ.get(xdg_var, "").strip()
    base = Path(xdg) if xdg and os.path.isabs(xdg) else xdg_fallback
    return base / "retrobox"


SYSCONF_DIR: Final[Path] = Path(os.environ.get("RETROBOX_SYSCONFDIR", "").strip() or "/etc/retrobox")
CONFIG_DIR: Final[Path] = _resolve_dir("RETROBOX_CONFIGDIR", "XDG_CONFIG_HOME", _XDG_CONFIG)
DATA_DIR: Final[Path] = _resolve_dir("RETROBOX_DATADIR", "XDG_DATA_HOME", _XDG_DATA)
STATE_DIR: Final[Path] = _resolve_dir("RETROBOX_STATEDIR", "XDG_STATE_HOME", _XDG_STATE)

# Make sure the mutable directories exist. A failure here must not break
# the import: whoever needs the directory will report a meaningful error
# when it tries to use it.
for _dir in (CONFIG_DIR, DATA_DIR, STATE_DIR):
    try:
        _dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

SHARE_DIR: Final[Path] = RETROBOX_ROOTDIR / "share"
LIBEXEC_DIR: Final[Path] = RETROBOX_ROOTDIR / "libexec"
BIN_DIR: Final[Path] = RETROBOX_ROOTDIR / "bin"
LIB_DIR: Final[Path] = RETROBOX_ROOTDIR / "lib"

# Layers, lowest priority first (see above).
CONFIG_LAYERS: Final[tuple[Path, ...]] = (SHARE_DIR, SYSCONF_DIR, CONFIG_DIR)


def layered_dirs(subdir: str) -> list[Path]:
    """The existing `subdir` of every layer, lowest priority first."""
    return [d for d in (layer / subdir for layer in CONFIG_LAYERS) if d.is_dir()]


def layered_file(relpath: str) -> Path | None:
    """The highest-priority existing file `relpath`, or None."""
    for layer in reversed(CONFIG_LAYERS):
        candidate = layer / relpath
        if candidate.is_file():
            return candidate
    return None


def layered_files(subdir: str, pattern: str = "*") -> dict[str, Path]:
    """
    Merge the files matching `pattern` under `subdir` (recursively) across
    layers: {relative path -> file}, where a later layer replaces an earlier
    one's file of the same relative path. Sorted by relative path.
    """
    found: dict[str, Path] = {}
    for base in layered_dirs(subdir):
        for path in base.rglob(pattern):
            if path.is_file():
                found[path.relative_to(base).as_posix()] = path
    return dict(sorted(found.items()))


# ---------------------------------------------------------------------------
# Bootstrap: retrobox.ini must be applied BEFORE computing any Final
# constants that may be overridden through its [environ] section (here and
# in _configgen.py / _frontend.py / _gamepadly.py, which import
# RETROBOX_ROOTDIR / SHARE_DIR / DATA_DIR from here).
# ---------------------------------------------------------------------------
_PATHS_CONFIG: Final[CaseSensitiveConfigParser] = _load_layered_ini(
    _ini_files(SYSCONF_DIR, CONFIG_DIR)
)
_bootstrap_env(_PATHS_CONFIG)

# ---------------------------------------------------------------------------
# Installation paths (same as in batocera)
# ---------------------------------------------------------------------------
ENV_FILE: Final[Path] = CONFIG_DIR / ".env"


def _resolve_runtime_dir() -> Path:
    """
    Per-user directory for ephemeral files (generated configs, wrapper scripts,
    overlays...): RETROBOX_RUNTIME_DIR > $XDG_RUNTIME_DIR/retrobox >
    <tmp>/retrobox-<uid>. Always private (0700): never a shared, predictable
    path in /tmp.
    """
    override = os.environ.get("RETROBOX_RUNTIME_DIR", "").strip()
    if override:
        path = Path(override)
    else:
        xdg = os.environ.get("XDG_RUNTIME_DIR", "").strip()
        if xdg and os.path.isabs(xdg) and os.access(xdg, os.W_OK):
            path = Path(xdg) / "retrobox"
        else:
            path = Path(tempfile.gettempdir()) / f"retrobox-{os.getuid()}"
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        pass
    return path


RUNTIME_DIR: Final[Path] = _resolve_runtime_dir()
RETROBOX_INI: Final[Path] = CONFIG_DIR / "retrobox.ini"  # the user's file; may not exist

DATAINIT_DIR: Final[Path] = SHARE_DIR / "datainit"
DEFAULTS_DIR: Final[Path] = SHARE_DIR / "configgen"

HOME_INIT: Final[Path] = DATAINIT_DIR / "system"
CONF_INIT: Final[Path] = HOME_INIT / "configs"
EMULATORS: Final[Path] = DATA_DIR / "emulators"  # emulator binaries (installers)
EMULATORS_CONFIG: Final[Path] = CONFIG_DIR / "emulators"  # <emu>/ = its XDG_CONFIG_HOME
ROMS: Final[Path] = get_configured_path("roms_dir", DATA_DIR / "roms")

IGNORED_SYSTEMS: Final[frozenset[str]] = get_ignored_systems()

CACHE: Final[Path] = _XDG_CACHE / "retrobox"
LOGS: Final[Path] = STATE_DIR / "logs"

HOOKS: Final[Path] = SHARE_DIR / "hooks" / "retrohook"


# ---------------------------------------------------------------------------
# Generic filesystem utilities
# ---------------------------------------------------------------------------
def mkdir_if_not_exists(directory: Path) -> None:
    """
    Create a directory and its parents if they do not exist.

    Handles edge cases where the path exists but is not a valid directory
    (e.g., broken symlink or regular file). If it's a broken symlink, it
    is removed. If it's a regular file, it is renamed with a timestamp
    backup to avoid data loss.

    Args:
        directory: The directory path to create.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        # If it's a broken symlink, remove it and create the directory
        if directory.is_symlink():
            directory.unlink()
            directory.mkdir(parents=True, exist_ok=True)
        else:
            # If it's a regular file, rename it to avoid data loss and create the directory
            backup_name = f"{directory.name}.bak_{int(time.time())}"
            directory.rename(directory.with_name(backup_name))
            directory.mkdir(parents=True, exist_ok=True)


def ensure_symlink(source: Path, link: Path) -> None:
    """
    Guarantee that a symlink exists: link -> source.

    Safety guarantees:
    - Does not delete non-empty directories.
    - Avoids symlink cycles.
    - Does not touch anything if it's already correct.

    Args:
        source: The target path the symlink should point to.
        link: The path where the symlink should be created.

    Raises:
        RuntimeError: If a symlink cycle is detected or if refusing to
                      replace a non-empty directory.
    """
    source = source.resolve()

    # --- 1. Avoid self-reference ---
    if link.resolve() == source:
        return

    # --- 2. Detect cycles (link inside source or vice versa) ---
    try:
        if source in link.resolve().parents:
            raise RuntimeError(f"Symlink loop detected: {link} -> {source}")
    except FileNotFoundError:
        # link does not exist yet → ok
        pass

    # --- 3. If it already exists ---
    if link.exists() or link.is_symlink():
        # --- Case A: already a symlink ---
        if link.is_symlink():
            try:
                if link.resolve() == source:
                    return  # already correct
            except FileNotFoundError:
                pass  # broken symlink → recreate it

            link.unlink()
            link.symlink_to(source)
            return

        # --- Case B: real directory ---
        if link.is_dir():
            # critical protection
            if any(link.iterdir()):
                raise RuntimeError(f"Refusing to replace non-empty directory: {link}")

            shutil.rmtree(link)
            link.symlink_to(source)
            return

        # --- Case C: regular file ---
        link.unlink()
        link.symlink_to(source)
        return

    # --- 4. Does not exist ---
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source)


@overload
def ensure_parents_and_open(
    file: Path, mode: OpenTextModeWriting | OpenTextModeUpdating
) -> Generator[TextIOWrapper, None, None]: ...


@overload
def ensure_parents_and_open(
    file: Path, mode: OpenBinaryModeUpdating
) -> Generator[BufferedRandom, None, None]: ...


@overload
def ensure_parents_and_open(
    file: Path, mode: OpenBinaryModeWriting
) -> Generator[BufferedWriter, None, None]: ...


@contextmanager
def ensure_parents_and_open(file: Path, mode: str) -> Generator[IO[Any], None, None]:
    """
    Ensure parent directories exist and open a file.

    Creates the parent directories of `file` if they do not exist, then
    opens the file with the given mode. This is a context manager that
    yields the file object.

    Args:
        file: The file path to open.
        mode: The mode in which to open the file (e.g., 'w', 'rb').

    Yields:
        The opened file object.
    """
    mkdir_if_not_exists(file.parent)
    # Explicitly set UTF-8 for text modes to avoid Pylint unspecified-encoding warnings
    encoding = "utf-8" if "b" not in mode else None
    with file.open(mode, encoding=encoding) as f:
        yield f