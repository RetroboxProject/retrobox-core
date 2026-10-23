
from typing import Final

from runtime.paths import BIOS, CHEATS, EMULATORS_CONFIG, ROMS, SAVES

_MELONDS_DIR: Final = EMULATORS_CONFIG / "melonds"
_MELONDS_XDG: Final = _MELONDS_DIR
_MELONDS_CFGDIR: Final = _MELONDS_XDG / "melonDS"
_MELONDS_SAVES: Final = SAVES / "nds"
_MELONDS_ROMS: Final = ROMS / "nds"
_MELONDS_CHEATS: Final = CHEATS / "melonDS"

# Config file path
MELONDS_CFG = _MELONDS_CFGDIR / "melonDS.toml"

# nds bios paths
NDS_FIRMWARE: Final = BIOS / "firmware.bin"
NDS_ARM7_BIOS: Final = BIOS / "bios7.bin"
NDS_ARM9_BIOS: Final = BIOS / "bios9.bin"

# dsi bios paths
DSI_FIRMWARE: Final = BIOS / "dsi_firmware.bin"
DSI_ARM9_BIOS: Final = BIOS / "dsi_bios9.bin"
DSI_ARM7_BIOS: Final = BIOS / "dsi_bios7.bin"
DSI_NAND: Final = BIOS / "dsi_nand.bin"
