from typing import Final

from retrobox.paths import BIOS, EMULATORS_CONFIG, SAVES


_SCUMMVM_DIR: Final = EMULATORS_CONFIG / "scummvm"
_SCUMMVM_XDG: Final = _SCUMMVM_DIR
_SCUMMVM_CFGDIR: Final = _SCUMMVM_XDG / "scummvm"
SCUMMVM_CFG: Final = _SCUMMVM_CFGDIR / "scummvm.ini"
_SCUMMVM_EXTRA: Final = BIOS / "scummvm" / "extra"
_SCUMMVM_SAVES: Final = SAVES / "scummvm"
