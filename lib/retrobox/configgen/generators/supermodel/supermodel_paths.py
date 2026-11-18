from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import EMULATORS, SAVES

_SUPERMODEL_EMUDIR: Final = EMULATORS / 'supermodel'
_SUPERMODEL_CFGDIR: Final = _SUPERMODEL_EMUDIR / 'Config'
_SUPERMODEL_SAVES: Final = SAVES / 'supermodel'
# portable: it runs from its folder (Config/Games.xml, NVRAM, Saves)
SUPERMODEL: Final = EmulatorBinary("supermodel", ("supermodel",), installer="supermodel3",
                                   appimage=False, outside=False)

_SUPERMODEL_CFG = _SUPERMODEL_CFGDIR / "Supermodel.ini"
