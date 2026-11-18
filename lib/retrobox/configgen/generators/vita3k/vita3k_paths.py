from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import EMULATORS_CONFIG, SAVES


_VITA3K_XDG: Final =  EMULATORS_CONFIG / 'vita3k'
_VITA3K_CFGDIR: Final = _VITA3K_XDG / 'vita3k'
_VITA3K_SAVES: Final = SAVES / 'psvita'
VITA3K_CFG: Final = _VITA3K_CFGDIR / 'config.yml'
VITA3K: Final = EmulatorBinary("vita3k", ("Vita3K", "vita3k"), installer="vita3k")
