from pathlib import Path
from typing import Final

from runtime.paths import EMULATORS_CONFIG, ROMS, SAVES

# Set the paths using Path objects
_SHADPS4_DIR: Final = EMULATORS_CONFIG / "shadps4"
_SHADPS4_XDG: Final = _SHADPS4_DIR
_SHADPS4_CFGDIR: Final = _SHADPS4_XDG / "shadps4"
_SHADPS4_USER_CFGDIR: Final = _SHADPS4_CFGDIR / "user"
SHADPS4_BIN: Final = Path("/usr/bin/shadps4/shadps4")
SHADPS4_TOML: Final = _SHADPS4_USER_CFGDIR / "config.toml"
SHADPS4_SAVES: Final = SAVES / "ps4"
SHADPS4_ROMS: Final = ROMS / "ps4"
SHADPS4_DLCS: Final = ROMS / "ps4_dlc"
