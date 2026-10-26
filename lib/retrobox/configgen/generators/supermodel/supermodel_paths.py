from typing import Final

from retrobox.paths import EMULATORS, SAVES

_SUPERMODEL_EMUDIR: Final = EMULATORS / 'supermodel'
_SUPERMODEL_CFGDIR: Final = _SUPERMODEL_EMUDIR / 'Config'
_SUPERMODEL_SAVES: Final = SAVES / 'supermodel'
SUPERMODEL_BIN: Final = _SUPERMODEL_EMUDIR / "supermodel"

_SUPERMODEL_CFG = _SUPERMODEL_CFGDIR / "Supermodel.ini"
