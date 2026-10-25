"""The directories Retrobox shares with processes that are not Python.

`runtime.paths` is the single source of truth for every location. Shell
scripts (hooks, emulator config helpers, the installers under setup/) can't
import it, so the resolved values are handed over as RETROBOX_* environment
variables, in two ways:

  * importing `runtime.paths` exports them to os.environ, so every child
    process of the launcher inherits them;
  * `python3 -m runtime.paths --shell` prints them as `export` lines, which
    is what setup/lib/paths.sh evals when no launcher is involved.
"""

from __future__ import annotations

from pathlib import Path

from ._base import (
    CONFIG_DIR,
    DATA_DIR,
    EMULATORS,
    EMULATORS_CONFIG,
    RETROBOX_INI,
    RETROBOX_ROOTDIR,
    ROMS,
    RUNTIME_DIR,
    STATE_DIR,
    SYSCONF_DIR,
)
from ._configgen import _DECORATIONS_DEF_DIR, _DECORATIONS_DIR, BIOS, SAVES, SCREENSHOTS
from ._frontend import ES_EXECUTABLE, FRONTEND_DIR, FRONTEND_HOME, MUSIC_DIR, THEMES_DIR


def exported_environment() -> dict[str, Path]:
    """Return every RETROBOX_* variable shared with non-Python processes."""
    return {
        "RETROBOX_ROOTDIR": RETROBOX_ROOTDIR,
        "RETROBOX_SYSCONFDIR": SYSCONF_DIR,
        "RETROBOX_CONFIGDIR": CONFIG_DIR,
        "RETROBOX_DATADIR": DATA_DIR,
        "RETROBOX_STATEDIR": STATE_DIR,
        "RETROBOX_RUNTIME_DIR": RUNTIME_DIR,
        "RETROBOX_INI": RETROBOX_INI,
        "RETROBOX_ROMS_DIR": ROMS,
        "RETROBOX_SAVES_DIR": SAVES,
        "RETROBOX_BIOS_DIR": BIOS,
        "RETROBOX_EMULATORS_DIR": EMULATORS,
        "RETROBOX_EMUCONFIG_DIR": EMULATORS_CONFIG,
        "RETROBOX_THEMES_DIR": THEMES_DIR,
        "RETROBOX_MUSIC_DIR": MUSIC_DIR,
        "RETROBOX_SCREENSHOTS_DIR": SCREENSHOTS,
        "RETROBOX_BEZELS_DIR": _DECORATIONS_DIR,
        "RETROBOX_BEZELS_DEFAULT_DIR": _DECORATIONS_DEF_DIR,
        "RETROBOX_FRONTEND_DIR": FRONTEND_DIR,
        "RETROBOX_FRONTEND_HOME": FRONTEND_HOME,
        "RETROBOX_ES_EXECUTABLE": ES_EXECUTABLE,
    }
