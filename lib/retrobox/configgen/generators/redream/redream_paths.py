
from typing import Final

from retrobox.paths import EMULATORS, ROMS

REDREAM_DIR: Final = EMULATORS / "redream"
REDREAM_BIN: Final = REDREAM_DIR / "redream"
_REDREAM_ROMS: Final = ROMS / "dreamcast"
REDREAM_CFG = REDREAM_DIR / "redream.cfg"
