
from typing import Final

from runtime.paths import EMULATORS_CONFIG

_DUCKSTATION_DIR: Final = EMULATORS_CONFIG / "duckstation"
_DUCKSTATION_XDG: Final = _DUCKSTATION_DIR
_DUCKSTATION_CFGDIR: Final = _DUCKSTATION_XDG / "duckstation"
DUCKSTATION_CFG: Final = _DUCKSTATION_CFGDIR / "settings.ini"
DUCKSTATION_BIN: Final = _DUCKSTATION_DIR / "app" / "bin" / "duckstation"
