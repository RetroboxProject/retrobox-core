from pathlib import Path
from typing import Final

from runtime.paths import EMULATORS_CONFIG


_DOSBOX_DIR: Final = EMULATORS_CONFIG / 'dosbox'
_DOSBOX_XDG: Final = _DOSBOX_DIR
_DOSBOX_CFGDIR: Final = _DOSBOX_XDG / 'dosbox'
# Use a separate file from dosbox.conf to avoid overwriting by dosbox
DOSBOX_CFG: Final = _DOSBOX_CFGDIR / 'dosbox-custom.conf'
DOSBOX_BIN: Final = Path("/usr/bin/dosbox")