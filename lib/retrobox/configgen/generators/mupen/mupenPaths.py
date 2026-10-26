from __future__ import annotations

from typing import Final

from retrobox.paths import DATAINIT_DIR, EMULATORS_CONFIG, SAVES

MUPEN_CONFIG_DIR: Final = EMULATORS_CONFIG / 'mupen64plus'
MUPEN_CUSTOM: Final = MUPEN_CONFIG_DIR / 'mupen64plus.cfg'
MUPEN_INPUT: Final = MUPEN_CONFIG_DIR / 'InputAutoCfg.ini'
MUPEN_SAVES: Final = SAVES / 'n64'
MUPEN_USER_MAPPING: Final = MUPEN_CONFIG_DIR / 'input.xml'
MUPEN_SYSTEM_MAPPING: Final = DATAINIT_DIR / 'system' / 'configs' / 'mupen64' / 'input.xml'
