from typing import Final
from retrobox.paths import DEFAULTS_DIR, EMULATORS, ROMS

MODEL2_ROMS: Final = ROMS / "model2"

M2EMU_WINEPREFIX: Final = EMULATORS / "model2emu"
M2EMU_EMUDIR: Final = M2EMU_WINEPREFIX / "drive_c" / "model2emu"
M2EMU_RESOURCES: Final = DEFAULTS_DIR / "data" / "model2emu"