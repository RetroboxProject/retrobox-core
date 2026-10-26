from typing import Final

from retrobox.paths import EMULATORS, EMULATORS_CONFIG, SAVES


_VITA3K_DIR: Final =  EMULATORS / 'vita3k'
_VITA3K_XDG: Final =  EMULATORS_CONFIG / 'vita3k'
_VITA3K_CFGDIR: Final = _VITA3K_XDG / 'vita3k'
_VITA3K_SAVES: Final = SAVES / 'psvita'
VITA3K_CFG: Final = _VITA3K_CFGDIR / 'config.yml'
VITA3K_BIN: Final = _VITA3K_DIR / "app"/ "AppRun"
