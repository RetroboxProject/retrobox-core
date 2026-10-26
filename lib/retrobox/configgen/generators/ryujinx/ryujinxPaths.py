from typing import Final

from retrobox.paths import DEFAULTS_DIR, EMULATORS, EMULATORS_CONFIG, SAVES

_RYUJINX_EMUDIR: Final = EMULATORS / "ryujinx"
RYUJINX_BIN: Final = _RYUJINX_EMUDIR / "ryujinx.AppImage"
_RYUJINX_XDG: Final = EMULATORS_CONFIG / 'ryujinx'

RYUJINX_CONFIG: Final = _RYUJINX_XDG / "Ryujinx"
RYUJINX_CONFIG_FILE: Final = RYUJINX_CONFIG / "Config.json"
RYUJINX_CONFIG_FILE_TPL: Final = DEFAULTS_DIR / "data" / "switch" / "Config.json.template"
RYUJINX_CONFIG_FILE_BFR: Final = RYUJINX_CONFIG / "Config.json.before"
RYUJINX_BIS: Final = RYUJINX_CONFIG / "bis"

RYUJINX_USER_DIR: Final = RYUJINX_BIS / "user"
RYUJINX_SYSTEM_DIR: Final = RYUJINX_BIS / "system"
RYUJINX_SYSTEM_CONFIG_DIR: Final = RYUJINX_CONFIG / "system"
RYUJINX_MODS_LINK: Final = RYUJINX_CONFIG / "mods"

RYUJINX_SAVE_BASE: Final = SAVES / "switch" / "ryujinx" / "save"

RYUJINX_USER_SAVES: Final = RYUJINX_SAVE_BASE / "save_user"
RYUJINX_SYSTEM_SAVES: Final = RYUJINX_SAVE_BASE / "save_system"
