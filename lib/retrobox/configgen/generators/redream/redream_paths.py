
from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import EMULATORS, ROMS

REDREAM_DIR: Final = EMULATORS / "redream"
# portable: it reads redream.cfg and keeps its data next to the executable
REDREAM: Final = EmulatorBinary("redream", ("redream",), installer="redream", appimage=False,
                                outside=False)
_REDREAM_ROMS: Final = ROMS / "dreamcast"
REDREAM_CFG = REDREAM_DIR / "redream.cfg"
