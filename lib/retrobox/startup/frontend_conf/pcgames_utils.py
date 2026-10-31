"""
Utilities for syncing installed PC games (Steam, Lutris, Heroic) with
EmulationStation by generating launcher files (.steam, .lynx, .heroic)
in the corresponding ROM directories.

Each store is synced according to `[core] <system>_sync` in retrobox.ini
(see SyncMode): `none`, `on-base-dir` or `follow-roms-dir`.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

from retrobox.paths import safe_mkdir

from retrobox.startup.frontend_conf.pcgames_paths import (
    _EPIC_JSON,
    _GOG_JSON,
    _HEROIC_SIDELOAD_JSON,
    _INVALID_FILENAME_CHARS,
    _LUTRIS_DB_CANDIDATES,
    _SKIP_NAME_RE,
    _STEAM_ROOTS,
    PCGAMES_SYSTEMS,
    SyncMode,
    get_sync_mode,
    pcgames_roms_dir,
)

_logger = logging.getLogger(__name__)


def _clear_name(name: str) -> str:
    """
    Remove invalid filename characters and strip surrounding whitespace.

    Args:
        name: The raw game name to sanitize.

    Returns:
        A filesystem-safe version of the name.
    """
    return name.translate(_INVALID_FILENAME_CHARS).strip()


def _write_heroic_link(target: Path, name: str, app_name: str, runner: str) -> None:
    """
    Write a .heroic launcher file for a given game.

    Args:
        target: Directory where the launcher file will be created.
        name: Display name of the game (used as the filename).
        app_name: Internal app identifier used by Heroic.
        runner: Heroic runner type (e.g., "legendary", "gog", "sideload").
    """
    name_clean = _clear_name(name)
    link = f"heroic://launch?appName={app_name}&runner={runner}"
    file_path = target / f"{name_clean}.heroic"
    file_path.write_text(link + "\n", encoding="utf-8")
    _logger.debug("[%s] %s.heroic -> %s", runner, name_clean, link)


def _load_json(path: Path) -> Any:
    """
    Safely load a JSON file, returning None on any failure.

    Args:
        path: Path to the JSON file to read.

    Returns:
        The parsed JSON data, or None if the file is missing or malformed.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.debug("Couldn't read %s: %s", path, exc)
        return None


def _vdf_get(text: str, key: str) -> str:
    """
    Extract a string value from a Valve Data File (VDF) formatted text.

    Args:
        text: The raw VDF text content.
        key: The key to search for.

    Returns:
        The associated value, or an empty string if not found.
    """
    match = re.search(rf'"{re.escape(key)}"\s*"([^"]*)"', text, re.IGNORECASE)
    return match.group(1) if match else ""


def _clear_pcgame_links(system_dir: Path, ext: str) -> None:
    """
    Remove all existing launcher files with the given extension in a directory.

    Used to ensure a clean import before regenerating launchers.

    Args:
        system_dir: The directory to clean.
        ext: File extension to delete (without the leading dot).
    """
    _logger.info("Deleting %s links for clean import: %s", ext, system_dir)

    if not system_dir.is_dir():
        return
    for f in system_dir.glob(f"*.{ext}"):
        f.unlink(missing_ok=True)


def lutris_es_sync(target: Path) -> int:
    """
    Scan games installed in Lutris (via its SQLite database) and generate
    a .lynx launcher file for each one in `target`.

    Args:
        target: Directory where .lynx files will be created.

    Returns:
        The number of launcher files generated.
    """
    lutris_db = next((c for c in _LUTRIS_DB_CANDIDATES if c.is_file()), None)
    if lutris_db is None:
        _logger.debug("Lutris database not found at: %s", _LUTRIS_DB_CANDIDATES)
        return 0

    _logger.debug("Lutris database found: %s", lutris_db)

    safe_mkdir(target)
    _clear_pcgame_links(target, "lynx")

    con = sqlite3.connect(str(lutris_db))
    try:
        rows = con.execute(
            "SELECT id, name, runner FROM games WHERE installed=1 ORDER BY name;"
        ).fetchall()
    finally:
        con.close()

    total = 0
    for game_id, name, runner in rows:
        if not game_id or not name:
            continue
        name_clean = _clear_name(name)
        link = f"lutris:rungameid/{game_id}"
        file_path = target / f"{name_clean}.lynx"
        file_path.write_text(link + "\n", encoding="utf-8")
        _logger.debug("[%s] %s.lynx -> %s", runner or "no runner", name_clean, link)
        total += 1

    _logger.info("%d Lutris launchers generated at %s", total, target)
    return total


def _steam_libraries(steam_root: Path) -> list[Path]:
    """
    List the Steam library folders, the root one first and without duplicates.

    Args:
        steam_root: The Steam installation directory.

    Returns:
        The library directories (empty if libraryfolders.vdf is missing).
    """
    library_vdf = next(
        (
            candidate
            for candidate in (
                steam_root / "steamapps" / "libraryfolders.vdf",
                steam_root / "libraryfolder.vdf",
            )
            if candidate.is_file()
        ),
        None,
    )
    if library_vdf is None:
        _logger.debug(
            "Couldn't find Steam library files (libraryfolders.vdf / libraryfolder.vdf)"
        )
        return []

    _logger.debug("Steam library read from: %s", library_vdf)
    vdf_text = library_vdf.read_text(encoding="utf-8", errors="ignore")
    paths = [steam_root, *map(Path, re.findall(r'"path"\s*"([^"]*)"', vdf_text, re.IGNORECASE))]
    return list(dict.fromkeys(paths))


def _sync_steam_library(steamapps_dir: Path, target: Path) -> int:
    """
    Write a .steam launcher in `target` for each game of one Steam library.

    Args:
        steamapps_dir: The library's steamapps directory.
        target: Directory where .steam files will be created.

    Returns:
        The number of launcher files generated.
    """
    total = 0
    for acf in sorted(steamapps_dir.glob("appmanifest_*.acf")):
        text = acf.read_text(encoding="utf-8", errors="ignore")
        appid = _vdf_get(text, "appid")
        name = _vdf_get(text, "name")
        if not appid or not name:
            continue
        if _SKIP_NAME_RE.search(name):
            _logger.debug("Skipping: %s (appid: %s)", name, appid)
            continue

        clean_name = _clear_name(name)
        link = f"steam://rungameid/{appid}"
        (target / f"{clean_name}.steam").write_text(link, encoding="utf-8")
        _logger.debug("%s.steam -> %s", clean_name, link)
        total += 1

    if total == 0:
        _logger.info("No Steam games found in: %s", steamapps_dir)
    return total


def steam_es_sync(target: Path) -> int:
    """
    Scan games installed in Steam (across all libraries) and generate
    a .steam launcher file for each one in `target`.

    Args:
        target: Directory where .steam files will be created.

    Returns:
        The number of launcher files generated.
    """
    steam_root = next((r for r in _STEAM_ROOTS if (r / "steamapps").is_dir()), None)
    if steam_root is None:
        _logger.debug("Steam installation not found at: %s", _STEAM_ROOTS)
        return 0

    _logger.debug("Steam found at: %s", steam_root)
    _clear_pcgame_links(target, "steam")

    libraries = [lib / "steamapps" for lib in _steam_libraries(steam_root)]
    libraries = [lib for lib in libraries if lib.is_dir()]
    if not libraries:
        return 0

    safe_mkdir(target)
    total = 0
    for steamapps_dir in libraries:
        _logger.debug("Library: %s", steamapps_dir)
        total += _sync_steam_library(steamapps_dir, target)

    _logger.info(
        "%d Steam launchers generated at %s (%d scanned libraries)",
        total, target, len(libraries),
    )
    return total


def heroic_es_sync(target: Path) -> int:
    """
    Scan games installed in Heroic (Epic/legendary, GOG, and sideload) and
    generate a .heroic launcher file for each one in `target`.

    Args:
        target: Directory where .heroic files will be created.

    Returns:
        The number of launcher files generated.
    """
    safe_mkdir(target)
    _clear_pcgame_links(target, "heroic")

    total = 0

    # Epic Games (legendary)
    data = _load_json(_EPIC_JSON)
    if data is not None:
        for entry in data.values():
            app_name = entry.get("app_name")
            title = entry.get("title")
            if not app_name or not title:
                continue
            _write_heroic_link(target, title, app_name, "legendary")
            total += 1
    else:
        _logger.info("Not found: %s", _EPIC_JSON)

    # GOG
    data = _load_json(_GOG_JSON)
    if data is not None:
        for entry in data.get("installed", []):
            app_name = entry.get("appName")
            install_path = entry.get("install_path", "")
            title = install_path.rstrip("/").split("/")[-1] if install_path else ""
            if not app_name or not title:
                continue
            _write_heroic_link(target, title, app_name, "gog")
            total += 1
    else:
        _logger.info("Not found: %s", _GOG_JSON)

    # Sideload / external apps
    data = _load_json(_HEROIC_SIDELOAD_JSON)
    if data is not None:
        for entry in data:
            app_name = entry.get("app_name")
            title = entry.get("title")
            if not app_name or not title:
                continue
            _write_heroic_link(target, title, app_name, "sideload")
            total += 1
    else:
        _logger.info("Not found: %s", _HEROIC_SIDELOAD_JSON)

    _logger.info("%d Heroic launchers generated at %s", total, target)
    return total


_SYNCERS: dict[str, Callable[[Path], int]] = {
    "steam": steam_es_sync,
    "lutris": lutris_es_sync,
    "heroic": heroic_es_sync,
}


def sync_pcgames() -> int:
    """
    Sync every PC-games store whose `[core] <system>_sync` is not `none`.

    The launchers go to pcgames_roms_dir(<system>), the same directory
    es_systems.cfg points EmulationStation at.

    Returns:
        The total number of launcher files generated.

    Raises:
        DirectoryCreationError: If a target directory can't be created.
    """
    total = 0
    for system in PCGAMES_SYSTEMS:
        mode = get_sync_mode(system)
        if mode is SyncMode.NONE:
            _logger.debug("Skipping %s sync ([core] %s_sync = none)", system, system)
            continue
        target = pcgames_roms_dir(system)
        _logger.info("Syncing %s games (%s) into %s", system, mode.value, target)
        total += _SYNCERS[system](target)
    return total
