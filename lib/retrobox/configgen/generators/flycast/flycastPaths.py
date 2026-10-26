from __future__ import annotations

from typing import Final

from retrobox.paths import BIOS, DEFAULTS_DIR, EMULATORS, EMULATORS_CONFIG, SAVES

_FLYCAST_EMUDIR: Final = EMULATORS / 'flycast'
FLYCAST_BIN: Final = _FLYCAST_EMUDIR / 'app' / 'bin' / 'flycast'
_FLYCAST_XDG: Final = EMULATORS_CONFIG / 'flycast'
FLYCAST_CONFIG_DIR: Final = _FLYCAST_XDG / 'flycast'
FLYCAST_MAPPING: Final = FLYCAST_CONFIG_DIR / 'mappings'
FLYCAST_CONFIG: Final = FLYCAST_CONFIG_DIR / 'emu.cfg'
FLYCAST_SAVES: Final = SAVES / 'dreamcast' / 'flycast'
FLYCAST_BIOS: Final = BIOS / 'dc'

FLYCAST_VMU_BLANK: Final = DEFAULTS_DIR / 'data' / 'dreamcast' / 'vmu_save_blank.bin'
FLYCAST_VMUA1: Final = FLYCAST_SAVES / 'vmu_save_A1.bin'
FLYCAST_VMUA2: Final = FLYCAST_SAVES / 'vmu_save_A2.bin'
