"""Locations of Keisho (Sega Model 1, 2 and 3): binary, configuration and saves.

The emulator is installed by ``tools/emulators/keisho.sh`` under its own
prefix (``bin/keisho`` and ``share/keisho/games.xml``), from the upstream
release tarball or from a source build.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from retrobox.paths import EMULATORS, EMULATORS_CONFIG, SAVES, SCREENSHOTS

if TYPE_CHECKING:
    from pathlib import Path

KEISHO_NAME: Final = "keisho"

_KEISHO_EMUDIR: Final = EMULATORS / KEISHO_NAME
KEISHO_PREFIX: Final = _KEISHO_EMUDIR / "app"
KEISHO_BIN: Final = KEISHO_PREFIX / "bin" / KEISHO_NAME
KEISHO_GAMES_DB: Final = KEISHO_PREFIX / "share" / KEISHO_NAME / "games.xml"
# written by the installer: which optional graphics backends the binary carries
KEISHO_BUILD_INFO: Final = KEISHO_PREFIX / "retrobox-build.ini"

# --config names a directory: the file in it is always keisho.ini
KEISHO_CFGDIR: Final = EMULATORS_CONFIG / KEISHO_NAME
KEISHO_CFG: Final = KEISHO_CFGDIR / "keisho.ini"

KEISHO_SCREENSHOTS: Final = SCREENSHOTS / KEISHO_NAME

# The emulator was called sm2-emu before it was renamed to Keisho.
_LEGACY_NAME: Final = "sm2-emu"
# the system the saves of sm2-emu were kept under: it only played Model 2
_LEGACY_SYSTEM: Final = "model2"

_logger = logging.getLogger(__name__)


def nvram_dir(system: str) -> Path:
    """Return where Keisho keeps the NVRAM and the save states of the games of ``system``."""
    return SAVES / system / KEISHO_NAME


def migrate_legacy_data() -> None:
    """Move the configuration, saves and screenshots of sm2-emu to their Keisho names.

    A directory is only moved when the Keisho one does not exist yet, so nothing
    is overwritten. The save states are converted by Keisho itself.
    """
    moves = (
        (EMULATORS_CONFIG / _LEGACY_NAME, KEISHO_CFGDIR),
        (SAVES / _LEGACY_SYSTEM / _LEGACY_NAME, nvram_dir(_LEGACY_SYSTEM)),
        (SCREENSHOTS / _LEGACY_NAME, KEISHO_SCREENSHOTS),
    )
    for old, new in moves:
        if old.is_dir() and not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
            _logger.info("moved %s to %s", old, new)
    old_ini = KEISHO_CFGDIR / f"{_LEGACY_NAME}.ini"
    if old_ini.is_file() and not KEISHO_CFG.exists():
        old_ini.rename(KEISHO_CFG)
