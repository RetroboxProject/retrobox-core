"""Locations of sm2-emu (Sega Model 2): binary, configuration and saves.

The emulator is installed by ``tools/emulators/sm2-emu.sh`` under its own
prefix (``bin/sm2-emu`` and ``share/sm2-emu/games.xml``), from the upstream
release tarball or from a source build.
"""

from __future__ import annotations

from typing import Final

from retrobox.paths import EMULATORS, EMULATORS_CONFIG, SAVES, SCREENSHOTS

SM2EMU_NAME: Final = "sm2-emu"

_SM2EMU_EMUDIR: Final = EMULATORS / SM2EMU_NAME
SM2EMU_PREFIX: Final = _SM2EMU_EMUDIR / "app"
SM2EMU_BIN: Final = SM2EMU_PREFIX / "bin" / SM2EMU_NAME
SM2EMU_GAMES_DB: Final = SM2EMU_PREFIX / "share" / SM2EMU_NAME / "games.xml"
# written by the installer: which optional graphics backends the binary carries
SM2EMU_BUILD_INFO: Final = SM2EMU_PREFIX / "retrobox-build.ini"

# --config names a directory: the file in it is always sm2-emu.ini
SM2EMU_CFGDIR: Final = EMULATORS_CONFIG / SM2EMU_NAME
SM2EMU_CFG: Final = SM2EMU_CFGDIR / "sm2-emu.ini"

SM2EMU_NVRAM: Final = SAVES / "model2" / SM2EMU_NAME
SM2EMU_SCREENSHOTS: Final = SCREENSHOTS / SM2EMU_NAME
