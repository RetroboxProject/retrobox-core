# libretro generator uses this, so it needs to be public

from typing import Final

from runtime.paths import EMULATORS_CONFIG

_HATARI_DIR: Final = EMULATORS_CONFIG / "hatari"
_HATARI_XDG: Final = _HATARI_DIR
_HATARI_CFGDIR: Final = _HATARI_XDG / "hatari"
HATARI_CFG: Final = _HATARI_CFGDIR / "hatari.cfg"
