"""Paths of Mupen64Plus: its installation, its configuration and its saves."""

from pathlib import Path
from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import EMULATORS_CONFIG, SAVES

# it needs the plugins and the data of Retrobox's own build (with batocera's patches), so
# neither a distribution's package nor an AppImage will do
MUPEN64PLUS: Final = EmulatorBinary(
    "mupen64plus", ("mupen64plus",), installer="mupen64plus", appimage=False, outside=False
)

MUPEN64PLUS_CONFIG_DIR: Final[Path] = EMULATORS_CONFIG / "mupen64plus"
MUPEN64PLUS_CONFIG: Final[Path] = MUPEN64PLUS_CONFIG_DIR / "mupen64plus.cfg"
# save states, SRAM and memory packs
MUPEN64PLUS_SAVES: Final[Path] = SAVES / "n64" / "mupen64"
