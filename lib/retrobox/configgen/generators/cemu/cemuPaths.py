from __future__ import annotations

from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import BIOS, EMULATORS_CONFIG, ROMS, SAVES

_CEMU_XDG: Final = EMULATORS_CONFIG / 'cemu'
CEMU: Final = EmulatorBinary("cemu", ("cemu", "Cemu"), installer="cemu")
CEMU_CONFIG: Final  = _CEMU_XDG / 'Cemu'
CEMU_ROMDIR: Final = ROMS / 'wiiu'
CEMU_SAVES: Final = SAVES / 'wiiu'
CEMU_BIOS: Final = BIOS / 'Cemu'
CEMU_CONTROLLER_PROFILES: Final = CEMU_CONFIG / 'controllerProfiles'
