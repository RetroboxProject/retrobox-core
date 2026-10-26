from __future__ import annotations

from typing import Final

from retrobox.paths import EMULATORS, EMULATORS_CONFIG

# directorios y ejecutable de retroarch y su config
_RETROARCH_DIR: Final = EMULATORS / "retroarch"
_RETROARCH_BIN: Final = _RETROARCH_DIR / "app" / "bin" / "retroarch"
_RETROARCH_XDG: Final = EMULATORS_CONFIG / 'retroarch'
_RETROARCH_CFGDIR: Final = _RETROARCH_XDG / "retroarch"

_RETROARCH_SHARE: Final = _RETROARCH_DIR / "app" / "share" / "retroarch"

# configs de retroarch que generamos en el configgen
RETROARCH_CFG: Final = _RETROARCH_CFGDIR / 'retroarch.cfg'
RETROARCH_CORE_CUSTOM: Final = _RETROARCH_CFGDIR / 'cores' / 'retroarch-core-options.cfg'
RETROARCH_OVERLAY_CONFIG: Final = _RETROARCH_CFGDIR / 'overlay.cfg'

# Ajustes "nucleares" que se fuerzan en TODOS los lanzamientos vía --appendconfig,
# siempre el último de la lista, para que ganen sin importar lo que RetroArch
# haya persistido en retroarch.cfg (p.ej. por config_save_on_exit) ni lo que
# el usuario haya tocado desde el propio menú de RetroArch.
RETROARCH_FORCED_CFG: Final = _RETROARCH_CFGDIR / 'retroarch-forced.cfg'

# assets de retroarch
RETROARCH_CORES: Final = _RETROARCH_SHARE / 'cores'
RETROARCH_SHARE: Final = _RETROARCH_SHARE / 'cores'
RETROARCH_ASSETS:    Final = _RETROARCH_SHARE / 'assets'
RETROARCH_AUTOCONFIG: Final = _RETROARCH_SHARE / 'autoconfig'
RETROARCH_SHADERS: Final = _RETROARCH_SHARE / 'shaders'

_RETROARCH_VIDEO_FILTERS: Final = _RETROARCH_SHARE / 'filters' / 'video'
_RETROARCH_AUDIO_FILTERS: Final = _RETROARCH_SHARE / 'filters' / 'audio'