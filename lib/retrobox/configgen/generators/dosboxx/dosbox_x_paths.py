from typing import Final

from retrobox.paths import EMULATORS_CONFIG


_DOSBOX_X_EMUDIR: Final = EMULATORS_CONFIG / 'dosbox-x'
_DOSBOX_X_XDG: Final = _DOSBOX_X_EMUDIR
_DOSBOX_X_CFGDIR: Final = _DOSBOX_X_XDG / "dosbox"
_DOSBOX_X_CFG: Final = _DOSBOX_X_CFGDIR / 'dosboxx.conf'
