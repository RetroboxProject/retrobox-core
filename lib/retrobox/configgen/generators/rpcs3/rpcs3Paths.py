from __future__ import annotations

from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import EMULATORS_CONFIG


_RPCS3_XDG: Final = EMULATORS_CONFIG / 'rpcs3'
_RPCS3_CFGDIR: Final = _RPCS3_XDG / 'rpcs3'
RPCS3_CONFIG: Final = _RPCS3_CFGDIR / 'config.yml'
RPCS3_CURRENT_CONFIG: Final = _RPCS3_CFGDIR / 'GuiConfigs' / 'CurrentSettings.ini'
RPCS3_CONFIG_INPUT: Final = _RPCS3_CFGDIR / 'config_input.yml'
RPCS3_CONFIG_EVDEV: Final = _RPCS3_CFGDIR / 'InputConfigs' / 'Evdev' / 'Default Profile.yml'
RPCS3: Final = EmulatorBinary("rpcs3", ("rpcs3",), installer="rpcs3")
