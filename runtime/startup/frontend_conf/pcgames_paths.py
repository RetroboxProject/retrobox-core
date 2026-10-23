"""Path/candidate lookup helpers for the Steam, Lutris and Heroic sync."""

import logging
import os
from pathlib import Path
import re

import yaml
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from runtime.paths import (
    _USER_HOME,
    _XDG_CONFIG,
    _XDG_DATA,
    FRONTEND_DIR,
    SYSTEMS_CONF_DIR,
    layered_file,
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

# systems_config YAML files that define each PC-games system, used to look
# up an optional ROM-directory override (see resolve_system_roms_dir below).
# The highest-priority layer (user > /etc/retrobox > shipped) wins.
_STEAM_SYSTEM_YAML = layered_file("systems_config/valve/steam.yaml") or SYSTEMS_CONF_DIR / "valve" / "steam.yaml"
_LUTRIS_SYSTEM_YAML = layered_file("systems_config/lutris/lutris.yaml") or SYSTEMS_CONF_DIR / "lutris" / "lutris.yaml"
_HEROIC_SYSTEM_YAML = layered_file("systems_config/heroic/heroic.yaml") or SYSTEMS_CONF_DIR / "heroic" / "heroic.yaml"


def resolve_system_roms_dir(yaml_path: Path, system_key: str, default: Path) -> Path:
    """
    Resolve the ROM directory to use for a PC-games system, honoring an
    optional "path" override defined in its systems_config YAML file.

    This lets a system's ROM folder live somewhere other than under
    ROMS_DIR (e.g. on a separate disk that may not always be mounted),
    by declaring its own "path" in
    resources/systems_config/.../<system>.yaml:

        lutris:
          path: ../roms/lutris
          ...

    That "path" may be absolute, or relative to $RETROBOX_ROOT/frontend
    (FRONTEND_DIR) -- the same base EmulationStation resolves "path"
    against for the equivalent entries in es_systems.cfg.

    If the override resolves to a directory that doesn't exist yet (e.g.
    its disk isn't mounted) or isn't writable, `default` is used instead.

    Args:
        yaml_path: Path to the system's YAML definition file.
        system_key: Top-level key inside the YAML (e.g. "lutris").
        default: Directory to fall back to if the YAML defines no
            override, the override isn't usable, or the YAML can't be
            read/parsed.

    Returns:
        The resolved Path to use as the sync target.
    """
    if not yaml_path.is_file():
        return default

    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (OSError, ScannerError, ParserError) as exc:
        _logger.debug("Couldn't read %s: %s", yaml_path, exc)
        return default

    if not isinstance(data, dict):
        return default

    sys_content = data.get(system_key)
    if not isinstance(sys_content, dict):
        return default

    raw_path = sys_content.get("path")
    if not raw_path:
        return default

    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = (FRONTEND_DIR / path).resolve()

    if not _is_usable_roms_dir(path):
        _logger.warning(
            "Alternate ROMs path for '%s' (%s, from %s) doesn't exist or isn't "
            "writable, falling back to %s",
            system_key, path, yaml_path, default,
        )
        return default

    if path != default:
        _logger.info(
            "Using alternate ROMs path for '%s' (from %s): %s",
            system_key, yaml_path, path,
        )

    return path


def _is_usable_roms_dir(path: Path) -> bool:
    """
    Check whether `path` is a directory that can actually be written to.

    Deliberately does NOT create `path` if it's missing: for an override
    coming from an unmounted disk, the directory simply won't be there,
    and blindly mkdir-ing it would create a phantom folder on the wrong
    filesystem instead of surfacing the problem so we can fall back.

    Args:
        path: The candidate ROMs directory to check.

    Returns:
        True if `path` exists, is a directory, and is writable.
    """
    if not path.is_dir():
        return False
    return os.access(path, os.W_OK | os.X_OK)