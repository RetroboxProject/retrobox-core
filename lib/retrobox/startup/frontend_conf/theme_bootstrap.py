"""
Install (or update) the default EmulationStation theme, es-theme-iconic.

retrobox-core ships no theme, so on a fresh install EmulationStation would
start with nothing to draw. When neither the system-wide themes directory
(FRONTEND_DIR/themes, filled by theme packages) nor the user's one
(THEMES_DIR) holds a theme, the latest commit of es-theme-iconic is
downloaded as a ZIP archive into THEMES_DIR. `retrobox
--update-default-theme` downloads it again, replacing the installed copy
(or reinstalling it if it was removed).

Any failure is reported and startup carries on: a missing theme must never
prevent the frontend from starting, and a failed update leaves the
installed copy untouched.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Final

from retrobox.configgen.utils.logger import OK
from retrobox.paths import FRONTEND_DIR, THEMES_DIR

_logger = logging.getLogger(__name__)

DEFAULT_THEME_NAME: Final = "es-theme-iconic"
DEFAULT_THEME_URL: Final = (
    "https://github.com/manu-creative-411/es-theme-iconic/archive/refs/heads/main.zip"
)

_SYSTEM_THEMES_DIR: Final = FRONTEND_DIR / "themes"
_THEME_MARKER: Final = "theme.xml"
_DOWNLOAD_TIMEOUT_S: Final = 60


def _is_theme(directory: Path) -> bool:
    """Whether `directory` is an EmulationStation theme (has a theme.xml)."""
    return (directory / _THEME_MARKER).is_file()


def _list_themes(themes_dir: Path) -> list[Path]:
    """
    List the themes installed in `themes_dir`.

    Args:
        themes_dir: Directory to scan.

    Returns:
        Its non-hidden theme subdirectories (none if `themes_dir` is
        missing or unreadable).
    """
    try:
        return sorted(
            entry
            for entry in themes_dir.iterdir()
            if not entry.name.startswith(".") and _is_theme(entry)
        )
    except FileNotFoundError:
        return []
    except OSError as exc:
        _logger.warning("Couldn't list themes in %s: %s", themes_dir, exc)
        return []


def _download(url: str, destination: Path) -> None:
    """
    Download `url` into the file `destination`.

    Raises:
        OSError: On any network or filesystem error (urllib's URLError
            and HTTPError are OSError subclasses).
    """
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as response, \
            destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _extract_theme(archive: Path, destination: Path) -> Path:
    """
    Extract a GitHub source archive and locate the theme inside it.

    zipfile drops absolute paths and ".." components while extracting, so
    the archive can't write outside `destination`.

    Args:
        archive: The downloaded ZIP file.
        destination: Empty directory to extract into.

    Returns:
        The theme's root directory (GitHub wraps the tree in a single
        "<repo>-<branch>" directory).

    Raises:
        zipfile.BadZipFile: If `archive` is not a valid ZIP file.
        ValueError: If the archive holds no theme.
    """
    with zipfile.ZipFile(archive) as zip_file:
        zip_file.extractall(destination)

    entries = [entry for entry in destination.iterdir() if entry.is_dir()]
    root = entries[0] if len(entries) == 1 else destination
    if not _is_theme(root):
        raise ValueError(f"no {_THEME_MARKER} at the root of the archive")
    return root


def _install_default_theme() -> bool:
    """
    Download the default theme into THEMES_DIR/<DEFAULT_THEME_NAME>.

    Everything happens in a hidden staging directory inside THEMES_DIR
    (same filesystem, so the final moves are renames); an installed copy
    is only replaced once the new one is complete and valid.

    Returns:
        True if the theme was installed.
    """
    target = THEMES_DIR / DEFAULT_THEME_NAME
    if target.is_symlink():
        _logger.error("%s is a symlink; not replacing it", target)
        return False

    try:
        THEMES_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".download-", dir=THEMES_DIR) as tmp:
            staging = Path(tmp)
            archive = staging / "theme.zip"
            extracted = staging / "extracted"
            extracted.mkdir()

            _logger.info("Downloading %s", DEFAULT_THEME_URL)
            _download(DEFAULT_THEME_URL, archive)
            theme_root = _extract_theme(archive, extracted)

            # The previous copy goes into the staging directory, which is
            # deleted on the way out.
            if target.exists():
                target.rename(staging / "previous")
            theme_root.rename(target)
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        _logger.error("Couldn't install %s: %s", DEFAULT_THEME_NAME, exc)
        return False

    _logger.log(OK, "Default theme installed: %s", target)
    return True


def ensure_default_theme(update: bool = False) -> bool:
    """
    Make sure EmulationStation has at least one theme.

    Args:
        update: Download the default theme again even if themes are
            installed, replacing (or reinstalling) its copy in THEMES_DIR.

    Returns:
        True if a theme is available afterwards, False otherwise.
    """
    if update:
        _logger.info("Updating the default theme (%s)", DEFAULT_THEME_NAME)
        if _install_default_theme():
            return True
        return bool(_list_themes(_SYSTEM_THEMES_DIR) or _list_themes(THEMES_DIR))

    themes = [*_list_themes(_SYSTEM_THEMES_DIR), *_list_themes(THEMES_DIR)]
    if themes:
        _logger.debug("EmulationStation themes found: %s", ", ".join(t.name for t in themes))
        return True

    _logger.warning(
        "No EmulationStation theme found in %s or %s; installing %s",
        _SYSTEM_THEMES_DIR, THEMES_DIR, DEFAULT_THEME_NAME,
    )
    if _install_default_theme():
        return True
    _logger.warning("EmulationStation will start without a theme")
    return False
