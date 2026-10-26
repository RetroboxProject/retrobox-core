from __future__ import annotations

from typing import Final

from retrobox.paths import BIOS, CHEATS, DEFAULTS_DIR, EMULATORS_CONFIG, ROMS, SAVES

# directorios y ejecutable de retroarch y su config
_MAME_DIR: Final = EMULATORS_CONFIG / "mame"
_MAME_BIN: Final = _MAME_DIR / "mame.AppImage"
_MAME_XDG: Final = _MAME_DIR
MAME_CONFIG: Final = _MAME_XDG / "retroarch"

MAME_SAVES: Final = SAVES / "mame"
MAME_BIOS: Final = BIOS / "mame"
MAME_CHEATS: Final = CHEATS / "mame"
MAME_ROMS: Final = ROMS / "mame"
MAME_DEFAULT_DATA: Final = DEFAULTS_DIR / "data" / "mame"
