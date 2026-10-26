
from typing import Final

from retrobox.paths import EMULATORS_CONFIG


_GSPLUS_DIR: Final = EMULATORS_CONFIG / 'gsplus'
_GSPLUS_XDG: Final = _GSPLUS_DIR
_GSPLUS_CFGDIR: Final = _GSPLUS_XDG / 'GSplus'
GSPLUS_CFG: Final = _GSPLUS_CFGDIR / 'config.txt'
