from typing import Final

from runtime.paths import BIOS, EMULATORS, EMULATORS_CONFIG

_PCSX2_DIR: Final = EMULATORS / 'pcsx2'
_PCSX2_XDG: Final = EMULATORS_CONFIG / 'pcsx2'
_PCSX2_CFGDIR: Final = _PCSX2_XDG / 'PCSX2'
_PCSX2_BIOS: Final = BIOS / "pcsx2" / "bios"
PCSX2_BIN: Final = _PCSX2_DIR / "app" / "AppRun"
PCSX2_CFG = _PCSX2_CFGDIR / 'inis' / "PCSX2.ini"
_PCSX2_TEXTURES = _PCSX2_CFGDIR / "textures"
PCSX2_PATCHES = _PCSX2_BIOS / "patches.zip"
PCSX2_DBFILE = _PCSX2_CFGDIR / "game_controller_db.txt"
