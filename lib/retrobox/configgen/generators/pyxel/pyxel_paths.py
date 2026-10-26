
from pathlib import Path
from typing import Final

from retrobox.paths import EMULATORS_CONFIG


_PYXEL_DIR: Final = EMULATORS_CONFIG / "pyxel"
_PYXEL_XDG: Final = _PYXEL_DIR
_PYXEL_CFGDIR: Final = _PYXEL_XDG / "pyxel"
PYXEL_BIN = Path("/usr/bin/pyxel")
