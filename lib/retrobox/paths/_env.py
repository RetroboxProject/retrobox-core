"""The directories Retrobox shares with processes that are not Python.

`retrobox.paths` is the single source of truth for every location. Shell
scripts (hooks, emulator config helpers, the installers under tools/) can't
import it, so the resolved values are handed over as RETROBOX_* environment
variables, in two ways:

  * importing `retrobox.paths` exports them to os.environ, so every child
    process of the launcher inherits them;
  * `python3 -m retrobox.paths --shell` prints them as `export` lines, which
    is what tools/lib/paths.sh evals when no launcher is involved.

A process that must resolve everything again from retrobox.ini (a Retrobox
started after the settings window changed it) gets fresh_environment()
instead, which leaves both of them out.
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
    _STARTUP_ENVIRON,
)
from ._configgen import _DECORATIONS_DEF_DIR, _DECORATIONS_DIR, BIOS, SAVES, SCREENSHOTS
from ._frontend import (
    ES_EXECUTABLE,
    ES_MENU_THEME,
    FRONTEND_DIR,
    FRONTEND_HOME,
    MUSIC_DIR,
    THEMES_DIR,
)

# Set by bin/retrobox: the RETROBOX_* variables the user exported himself, as
# opposed to the ones it resolved from retrobox.ini (tools/lib/paths.sh).
_USER_VARS: str = "RETROBOX_USER_VARS"


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
        # read by EmulationStation itself (patch 0006 of retrobox-emulationstation)
        "RETROBOX_ES_MENU_THEME": ES_MENU_THEME,
    }


def fresh_environment() -> dict[str, str]:
    """Return the environment for a process that must read retrobox.ini again.

    It is the environment this process started with, minus the variables
    resolved from retrobox.ini: those exported_environment() describes (unless
    the user set them himself, see bin/retrobox) and the [environ] entries,
    which were never in it. Without this, a child would inherit the values
    read before the file changed, and they win over the file.
    """
    user_vars = set(_STARTUP_ENVIRON.get(_USER_VARS, "").split())
    resolved = set(exported_environment()) - user_vars
    return {key: value for key, value in _STARTUP_ENVIRON.items() if key not in resolved}
