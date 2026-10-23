from typing import Final

from runtime.paths import EMULATORS_CONFIG

_OPENMSX_INST: Final = EMULATORS_CONFIG / 'openmsx'
_OPENMSX_XDG: Final = _OPENMSX_INST
_OPENMSX_HOMEDIR: Final = _OPENMSX_XDG / 'openmsx'
_OPENMSX_CFGDIR: Final = _OPENMSX_INST
