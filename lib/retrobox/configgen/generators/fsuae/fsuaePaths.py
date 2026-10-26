from __future__ import annotations

from typing import Final

from retrobox.paths import EMULATORS_CONFIG, BIOS, SAVES

_FSUAE_EMUDIR: Final = EMULATORS_CONFIG / 'fs-uae'
_FSUAE_XDG: Final = _FSUAE_EMUDIR
FSUAE_CONFIG_DIR: Final = _FSUAE_XDG / 'fs-uae'
FSUAE_BIOS_DIR: Final = BIOS / 'amiga'
FSUAE_SAVES: Final = SAVES / 'amiga'
