"""Paths of the Ares installation, its configuration and the folders it shares with Retrobox."""

from pathlib import Path
from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import BIOS, EMULATORS_CONFIG, SAVES, SCREENSHOTS

_ARES_XDG: Path = EMULATORS_CONFIG / 'ares'
_ARES_CFGDIR: Path = _ARES_XDG / "ares"
_ARES_CFG: Path = _ARES_CFGDIR / "settings.bml"
_ARES_FIRMWARE_INDEX: Path = _ARES_CFGDIR / "firmware_index.json"

_ARES_BIOS: Path = BIOS
_ARES_SAVES: Path = SAVES
_ARES_SCREENSHOTS: Path = SCREENSHOTS

# its data (share/ares) and librashader (lib/) are found next to the executable
ARES: Final = EmulatorBinary("ares", ("ares",), installer="ares")
