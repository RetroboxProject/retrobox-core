from __future__ import annotations

from pathlib import Path
from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import BIOS, CHEATS, DEFAULTS_DIR, EMULATORS_CONFIG, ROMS, SAVES

# MAME's folders, executable and configuration
_MAME_DIR: Final = EMULATORS_CONFIG / "mame"
MAME: Final = EmulatorBinary("mame", ("mame",))
# where distributions put MAME's data (hash, plugins, bgfx...) when it is not
# next to the executable, as it is in an upstream build
_MAME_SYSTEM_DATA: Final = (Path("/usr/share/games/mame"), Path("/usr/share/mame"))
_MAME_XDG: Final = _MAME_DIR
MAME_CONFIG: Final = _MAME_XDG / "retroarch"

MAME_SAVES: Final = SAVES / "mame"
MAME_BIOS: Final = BIOS / "mame"
MAME_CHEATS: Final = CHEATS / "mame"
MAME_ROMS: Final = ROMS / "mame"
MAME_DEFAULT_DATA: Final = DEFAULTS_DIR / "data" / "mame"


def mame_data_dir() -> Path:
    """MAME's own data folder: hash, plugins, bgfx, language, artwork and fonts."""
    executable = MAME.find()
    here = executable.resolve().parent if executable is not None else None
    if here is not None and (here / "plugins").is_dir():
        return here
    for folder in _MAME_SYSTEM_DATA:
        if folder.is_dir():
            return folder
    return here or _MAME_SYSTEM_DATA[-1]
