from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import BIOS, EMULATORS_CONFIG

_PCSX2_XDG: Final = EMULATORS_CONFIG / 'pcsx2'
_PCSX2_CFGDIR: Final = _PCSX2_XDG / 'PCSX2'
_PCSX2_BIOS: Final = BIOS / "pcsx2" / "bios"
PCSX2: Final = EmulatorBinary("pcsx2", ("pcsx2-qt", "pcsx2"), installer="pcsx2")
PCSX2_CFG = _PCSX2_CFGDIR / 'inis' / "PCSX2.ini"
PCSX2_PATCHES = _PCSX2_BIOS / "patches.zip"
PCSX2_DBFILE = _PCSX2_CFGDIR / "game_controller_db.txt"
