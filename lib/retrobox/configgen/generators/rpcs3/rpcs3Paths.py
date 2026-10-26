from __future__ import annotations

from pathlib import Path
from typing import Final

from retrobox.paths import EMULATORS, EMULATORS_CONFIG


_RPCS3_DIR: Final = EMULATORS / 'rpcs3'
_RPCS3_XDG: Final = EMULATORS_CONFIG / 'rpcs3'
_RPCS3_CFGDIR: Final = _RPCS3_XDG / 'rpcs3'
RPCS3_CONFIG: Final = _RPCS3_CFGDIR / 'config.yml'
RPCS3_CURRENT_CONFIG: Final = _RPCS3_CFGDIR / 'GuiConfigs' / 'CurrentSettings.ini'
RPCS3_CONFIG_INPUT: Final = _RPCS3_CFGDIR / 'config_input.yml'
RPCS3_CONFIG_EVDEV: Final = _RPCS3_CFGDIR / 'InputConfigs' / 'Evdev' / 'Default Profile.yml'
RPCS3_BIN: Final = _RPCS3_DIR / "app" / "AppRun"
