from __future__ import annotations

from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import EMULATORS, EMULATORS_CONFIG

# RetroArch's folders, executable and configuration
_RETROARCH_DIR: Final = EMULATORS / "retroarch"
# only Retrobox's install: the cores and assets are read from it
RETROARCH: Final = EmulatorBinary("retroarch", ("retroarch",), installer="retroarch",
                                  outside=False)
_RETROARCH_XDG: Final = EMULATORS_CONFIG / 'retroarch'
_RETROARCH_CFGDIR: Final = _RETROARCH_XDG / "retroarch"

_RETROARCH_SHARE: Final = _RETROARCH_DIR / "app" / "share" / "retroarch"

# the RetroArch configuration files configgen writes
RETROARCH_CFG: Final = _RETROARCH_CFGDIR / 'retroarch.cfg'
RETROARCH_CORE_CUSTOM: Final = _RETROARCH_CFGDIR / 'cores' / 'retroarch-core-options.cfg'
RETROARCH_OVERLAY_CONFIG: Final = _RETROARCH_CFGDIR / 'overlay.cfg'

# "Core" settings forced on EVERY launch through --appendconfig, always last
# in the list, so they win over whatever RetroArch saved in retroarch.cfg
# (e.g. through config_save_on_exit) and whatever the user changed from
# RetroArch's own menu.
RETROARCH_FORCED_CFG: Final = _RETROARCH_CFGDIR / 'retroarch-forced.cfg'

# the cores and their .info files: next to app/, not in it, so that installing
# RetroArch again keeps the cores downloaded one by one (retrobox.cores)
RETROARCH_CORES: Final = _RETROARCH_DIR / 'cores'
RETROARCH_INFO: Final = _RETROARCH_DIR / 'info'
# where the cores were before (inside app/), moved by retrobox.cores.migrate_legacy_cores
RETROARCH_LEGACY_CORES: Final = _RETROARCH_SHARE / 'cores'

# assets de retroarch
RETROARCH_ASSETS:    Final = _RETROARCH_SHARE / 'assets'
RETROARCH_AUTOCONFIG: Final = _RETROARCH_SHARE / 'autoconfig'
RETROARCH_SHADERS: Final = _RETROARCH_SHARE / 'shaders'

_RETROARCH_VIDEO_FILTERS: Final = _RETROARCH_SHARE / 'filters' / 'video'
_RETROARCH_AUDIO_FILTERS: Final = _RETROARCH_SHARE / 'filters' / 'audio'