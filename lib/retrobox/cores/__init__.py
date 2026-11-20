"""RetroArch's cores, downloaded one by one from the libretro buildbot.

EmulationStation's Content Downloader lists them in their own tab
(``libretro``), through ``retrobox-store``; see ``manager`` for where they go
and ``buildbot`` for where they come from.
"""

from .buildbot import BASE_CORES, BUILT_ON_ARM
from .manager import CoreError, Cores, migrate_legacy_cores

__all__ = ["BASE_CORES", "BUILT_ON_ARM", "CoreError", "Cores", "migrate_legacy_cores"]
