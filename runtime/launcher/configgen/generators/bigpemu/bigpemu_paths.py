from typing import Final

from runtime.paths import EMULATORS_CONFIG

_BIGPEMU_DIR: Final = EMULATORS_CONFIG / 'bigpemu'
_BIGPEMU_XDG: Final = _BIGPEMU_DIR
_BIGPEMU_CFGDIR: Final = _BIGPEMU_XDG / 'bigpemu'
BIGPEMU_CFG: Final = _BIGPEMU_CFGDIR / "bigpemu" / "BigPEmuConfig.bigpcfg"
