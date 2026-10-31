"""Paths, candidates and sync modes for the Steam, Lutris and Heroic sync."""

import functools
import logging
import os
import re
from enum import Enum
from pathlib import Path
from typing import Final

from retrobox.paths import (
    _USER_HOME,
    _XDG_CONFIG,
    _XDG_DATA,
    DATA_DIR,
    ROMS,
    get_ini_value,
)

_logger = logging.getLogger(__name__)


def _env_paths(var_name: str) -> tuple[Path, ...]:
    """Read an `os.pathsep`-separated environment variable into paths.

    Args:
        var_name: Name of the environment variable to read.

    Returns:
        A tuple of Path objects, or an empty tuple if the variable is
        unset or empty.
    """
    raw = os.environ.get(var_name, "")
    if not raw:
        return ()
    return tuple(Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip())


_LUTRIS_DB_CANDIDATES = (
    _XDG_DATA / "lutris" / "pga.db",
    _USER_HOME / ".var" / "app" / "net.lutris.Lutris" / ".local" / "share" / "lutris" / "pga.db",  # Flatpak
)

_INVALID_FILENAME_CHARS = str.maketrans({c: "-" for c in '/\\:*?"<>|'})

_STEAM_ROOTS = (
    *_env_paths("STEAM_LIBRARY_DIR"),
    _XDG_DATA / "Steam",
    _USER_HOME / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",  # Flatpak
)

_SKIP_NAME_RE = re.compile(
    r"proton|steam linux runtime|steamworks|redistributabl|pressure vessel|sniper|soldier",
    re.IGNORECASE,
)

_HEROIC_CONFIG = _XDG_CONFIG / "heroic"
_EPIC_JSON = _HEROIC_CONFIG / "legendaryConfig" / "legendary" / "installed.json"
_GOG_JSON = _HEROIC_CONFIG / "gog_store" / "installed.json"
_HEROIC_SIDELOAD_JSON = _HEROIC_CONFIG / "sideload_apps" / "library.json"


class SyncMode(str, Enum):
    """How the launchers of one PC-games store are synced into ES.

    Read from `[core] <system>_sync` in retrobox.ini (e.g. `steam_sync`).
    """

    # Don't sync anything (default).
    NONE = "none"
    # Always use <data_dir>/roms/<system>, wherever roms_dir points.
    ON_BASE_DIR = "on-base-dir"
    # Use <roms_dir>/<system>, i.e. follow the configured ROMs directory.
    FOLLOW_ROMS_DIR = "follow-roms-dir"


# ES system name (top-level key of its systems_config YAML) of each store.
PCGAMES_SYSTEMS: Final[tuple[str, ...]] = ("steam", "lutris", "heroic")

# The yes/no values these keys took in v0.0.25, mapped to the closest mode
# (that version synced into <roms_dir>/<system>).
_LEGACY_VALUES: Final[dict[str, SyncMode]] = {
    **dict.fromkeys(("true", "1", "yes", "on"), SyncMode.FOLLOW_ROMS_DIR),
    **dict.fromkeys(("false", "0", "no", "off"), SyncMode.NONE),
}


@functools.cache
def get_sync_mode(system: str) -> SyncMode:
    """
    Read the sync mode of a PC-games store from retrobox.ini.

    Args:
        system: ES system name of the store (one of PCGAMES_SYSTEMS).

    Returns:
        The configured SyncMode; SyncMode.NONE when the key is unset or
        holds an unknown value (the latter with a warning). The old
        yes/no values are still accepted, with a warning. Cached: the
        ini doesn't change while Retrobox runs, and this way an invalid
        value is only reported once.
    """
    key = f"{system}_sync"
    raw = get_ini_value("core", key, SyncMode.NONE.value).lower()
    try:
        return SyncMode(raw)
    except ValueError:
        pass

    expected = ", ".join(mode.value for mode in SyncMode)
    legacy = _LEGACY_VALUES.get(raw)
    if legacy is not None:
        _logger.warning(
            "[core] %s = %s is deprecated (expected one of: %s); using %s",
            key, raw, expected, legacy.value,
        )
        return legacy

    _logger.warning(
        "[core] %s = %s is not valid (expected one of: %s); not syncing %s",
        key, raw, expected, system,
    )
    return SyncMode.NONE


def pcgames_roms_dir(system: str) -> Path:
    """
    Directory that holds the launchers of a PC-games store.

    It is both where the sync writes and the `path` es_systems.cfg gives
    EmulationStation for that system, so both always agree. With
    SyncMode.NONE nothing is written, but the system still points at
    <roms_dir>/<system>, like any other system.

    Args:
        system: ES system name of the store (one of PCGAMES_SYSTEMS).

    Returns:
        <data_dir>/roms/<system> for SyncMode.ON_BASE_DIR, otherwise
        <roms_dir>/<system>.
    """
    if get_sync_mode(system) is SyncMode.ON_BASE_DIR:
        return DATA_DIR / "roms" / system
    return ROMS / system
