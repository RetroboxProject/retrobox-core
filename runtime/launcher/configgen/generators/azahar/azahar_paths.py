from __future__ import annotations
from typing import Final

from runtime.paths import EMULATORS_CONFIG, SAVES

_AZAHAR_DIR: Final  = EMULATORS_CONFIG / 'azahar'
_AZAHAR_XDG: Final = _AZAHAR_DIR
AZAHAR_BIN: Final  = _AZAHAR_DIR / 'azahar.AppImage'
AZAHAR_CONFIG: Final  = _AZAHAR_XDG / 'azahar-emu'
AZAHAR_INI: Final = AZAHAR_CONFIG / "qt-config.ini"
AZAHAR_SAVES: Final = SAVES / "3ds"