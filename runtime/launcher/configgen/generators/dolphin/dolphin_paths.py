from __future__ import annotations
from pathlib import Path
from typing import Final
from runtime.paths import BIOS, EMULATORS, EMULATORS_CONFIG, SAVES

_DOLPHIN_DIR:  Final = EMULATORS / 'dolphin-emu'
_DOLPHIN_XDG:  Final = EMULATORS_CONFIG / 'dolphin-emu'
_DOLPHIN_CFGDIR:  Final = _DOLPHIN_XDG / 'dolphin-emu'
_DOLPHIN_DATA:    Final = _DOLPHIN_DIR / 'app' / 'share' / 'dolphin-emu'
#DOLPHIN_BIN: Final = _DOLPHIN_DIR / "dolphin.AppImage"
DOLPHIN_BIN:     Final = _DOLPHIN_DIR / 'app' / "bin" / "dolphin-emu"
DOLPHIN_BIN_NOGUI:     Final = _DOLPHIN_DIR / 'app' / "bin" / "dolphin-emu-nogui"
#DOLPHIN_BIN:     Final = _DOLPHIN_DIR / "dolphin-emu-nogui"
#DOLPHIN_BIN: Final = Path("/usr/bin/dolphin-emu")
_DOLPHIN_LOCALE: Final = _DOLPHIN_DIR / 'app' / 'share' / 'locale'

DOLPHIN_INI:     Final = _DOLPHIN_CFGDIR / 'Dolphin.ini'
DOLPHIN_GFX_INI: Final = _DOLPHIN_CFGDIR / 'GFX.ini'
DOLPHIN_QT_INI:  Final = _DOLPHIN_CFGDIR / 'Qt.ini'

DOLPHIN_SAVES:   Final = SAVES / 'dolphin-emu'
DOLPHIN_SYSCONF: Final = _DOLPHIN_DATA / 'Wii' / 'shared2' / 'sys' / 'SYSCONF'
DOLPHIN_BIOS:    Final = BIOS / 'GC'

_DOLPHIN_WII_NAND = SAVES / "wii" / "nand"
_DOLPHIN_WII_RESPACKS = SAVES / "wii" / "resource_packs"
_DOLPHIN_WII_WFSDIR = SAVES / "wii" / "wfs_dir"
_DOLPHIN_WII_SDCARD_DIR: Final = SAVES / "wii" / "sdcard"
_DOLPHIN_WII_SDCARD_SYNC: Final = SAVES / "wii" / "sdcard_sync"
# GC memory cards (GCI folders) -> saves/gamecube
_DOLPHIN_GC_CARD_A = SAVES / "gamecube" / "Card A"
_DOLPHIN_GC_CARD_B = SAVES / "gamecube" / "Card B"
