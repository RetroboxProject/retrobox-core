from __future__ import annotations

from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import CONF_INIT, EMULATORS_CONFIG, SAVES

_PPSSPP_XDG: Final = EMULATORS_CONFIG / 'ppsspp'
PPSSPP: Final = EmulatorBinary("ppsspp", ("PPSSPPSDL", "ppsspp", "PPSSPPQt"), installer="ppsspp")
_PPSSPP_CFGDIR: Final = _PPSSPP_XDG / 'ppsspp'
_PPSSPP_PSPDIR: Final = SAVES / 'psp'
_PPSSPP_SYSDIR: Final =  _PPSSPP_PSPDIR / 'SYSTEM'
PPSSPP_CONFIG_INIT: Final = CONF_INIT / 'ppsspp' / 'PSP' / 'SYSTEM'
