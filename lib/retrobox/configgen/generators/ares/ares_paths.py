"""Paths of the Ares installation, its configuration and the folders it shares with Retrobox."""

from pathlib import Path

from retrobox.paths import BIOS, EMULATORS, EMULATORS_CONFIG, SAVES, SCREENSHOTS

_ARES_EMUDIR: Path = EMULATORS / "ares"
_ARES_XDG: Path = EMULATORS_CONFIG / 'ares'
_ARES_CFGDIR: Path = _ARES_XDG / "ares"
_ARES_LIBDIR: Path = _ARES_EMUDIR / "lib"
_ARES_CFG: Path = _ARES_CFGDIR / "settings.bml"
_ARES_FIRMWARE_INDEX: Path = _ARES_CFGDIR / "firmware_index.json"
_ARES_SHARE: Path = _ARES_EMUDIR / "share" / "ares"
_ARES_SHADERS_DIR: Path = _ARES_SHARE / "Shaders"

_ARES_BIOS: Path = BIOS
_ARES_SAVES: Path = SAVES
_ARES_SCREENSHOTS: Path = SCREENSHOTS

ARES_BIN: Path = _ARES_EMUDIR / "bin" / "ares"
