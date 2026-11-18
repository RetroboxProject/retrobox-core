from __future__ import annotations
from typing import Final
from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import BIOS, EMULATORS_CONFIG, SAVES

_DOLPHIN_XDG:  Final = EMULATORS_CONFIG / 'dolphin-emu'
_DOLPHIN_CFGDIR:  Final = _DOLPHIN_XDG / 'dolphin-emu'
DOLPHIN: Final = EmulatorBinary("dolphin-emu", ("dolphin-emu",), installer="dolphin-emu")
# the frontend without a GUI, for games: an AppImage only starts the GUI one
DOLPHIN_NOGUI: Final = EmulatorBinary("dolphin-emu", ("dolphin-emu-nogui",),
                                      installer="dolphin-emu", appimage=False)

DOLPHIN_INI:     Final = _DOLPHIN_CFGDIR / 'Dolphin.ini'
DOLPHIN_GFX_INI: Final = _DOLPHIN_CFGDIR / 'GFX.ini'
DOLPHIN_QT_INI:  Final = _DOLPHIN_CFGDIR / 'Qt.ini'
DOLPHIN_ACHIEVEMENTS_INI: Final = _DOLPHIN_CFGDIR / 'RetroAchievements.ini'

DOLPHIN_SAVES:   Final = SAVES / 'dolphin-emu'
DOLPHIN_BIOS:    Final = BIOS / 'GC'

_DOLPHIN_WII_NAND = SAVES / "wii" / "nand"
# the Wii settings, in the NAND Dolphin.ini points it at (NANDRootPath)
DOLPHIN_SYSCONF: Final = _DOLPHIN_WII_NAND / "shared2" / "sys" / "SYSCONF"
_DOLPHIN_WII_RESPACKS = SAVES / "wii" / "resource_packs"
_DOLPHIN_WII_WFSDIR = SAVES / "wii" / "wfs_dir"
_DOLPHIN_WII_SDCARD_DIR: Final = SAVES / "wii" / "sdcard"
_DOLPHIN_WII_SDCARD_SYNC: Final = SAVES / "wii" / "sdcard_sync"
# GC memory cards (GCI folders) -> saves/gamecube
_DOLPHIN_GC_CARD_A = SAVES / "gamecube" / "Card A"
_DOLPHIN_GC_CARD_B = SAVES / "gamecube" / "Card B"
