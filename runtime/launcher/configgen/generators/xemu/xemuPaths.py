from __future__ import annotations

from pathlib import Path
from typing import Final

from runtime.paths import SAVES, EMULATORS_CONFIG

XEMU_BIN: Final = Path('/usr/bin/xemu')
XEMU_SAVES: Final = SAVES / 'xbox'
XEMU_CONFIG: Final = EMULATORS_CONFIG / 'xemu' / 'xemu.toml'
