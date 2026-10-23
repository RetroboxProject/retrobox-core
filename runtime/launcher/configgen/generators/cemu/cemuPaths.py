from __future__ import annotations

from typing import Final

from runtime.paths import BIOS, EMULATORS, EMULATORS_CONFIG, ROMS, SAVES

_CEMU_EMUDIR: Final  = EMULATORS / 'cemu'
_CEMU_XDG: Final = EMULATORS_CONFIG / 'cemu'
CEMU_BIN: Final  = _CEMU_EMUDIR / 'cemu.AppImage'
CEMU_CONFIG: Final  = _CEMU_XDG / 'Cemu'
CEMU_ROMDIR: Final = ROMS / 'wiiu'
CEMU_SAVES: Final = SAVES / 'wiiu'
CEMU_BIOS: Final = BIOS / 'Cemu'
#CEMU_DATA_DIR: Final = Path('/usr/bin/cemu')
CEMU_CONTROLLER_PROFILES: Final = CEMU_CONFIG / 'controllerProfiles'
