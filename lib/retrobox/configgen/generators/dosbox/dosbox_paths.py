from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import EMULATORS_CONFIG


_DOSBOX_DIR: Final = EMULATORS_CONFIG / 'dosbox'
_DOSBOX_XDG: Final = _DOSBOX_DIR
_DOSBOX_CFGDIR: Final = _DOSBOX_XDG / 'dosbox'
# Use a separate file from dosbox.conf to avoid overwriting by dosbox
DOSBOX_CFG: Final = _DOSBOX_CFGDIR / 'dosbox-custom.conf'
DOSBOX: Final = EmulatorBinary("dosbox", ("dosbox",), appimage=False)