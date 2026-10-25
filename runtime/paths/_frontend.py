"""runtime.paths constants for the frontend (EmulationStation).

Covers the binary's location, generated configuration files, and
resource metadata (guns/wheels/gamesdb).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

from ._base import CONFIG_DIR, DATA_DIR, DEFAULTS_DIR, RETROBOX_ROOTDIR, RUNTIME_DIR

# FRONTEND_DIR: the (read-only) frontend install: binary, resources and the
# themes installed by theme packages (retrobox-core ships none).
# FRONTEND_HOME: EmulationStation's writable home (settings, generated
# es_systems.cfg, gamelists, collections), seeded from FRONTEND_DIR. It is
# configuration, so it lives under ~/.config/retrobox.
# THEMES_DIR / MUSIC_DIR: user content, under ~/.local/share/retrobox. The
# themes installed system-wide in FRONTEND_DIR/themes (e.g. by a retrobox theme
# package) are found by EmulationStation itself through `system.themes` in
# emulationstation.ini; nothing is linked.
FRONTEND_DIR: Final = RETROBOX_ROOTDIR / "frontend"
FRONTEND_HOME: Final = CONFIG_DIR / "frontend"
THEMES_DIR: Final = DATA_DIR / "themes"
MUSIC_DIR: Final = DATA_DIR / "music"

_USER_ES_DIR: Final = FRONTEND_HOME / ".emulationstation"
ES_SETTINGS_CFG: Final = _USER_ES_DIR / "es_settings.cfg"
ES_FEATURES_CFG: Final = _USER_ES_DIR / "es_features.cfg"
ES_SYSTEMS_CFG: Final = _USER_ES_DIR / "es_systems.cfg"
ES_FEATURES_TMP: Final = RUNTIME_DIR / "es_features.cfg"
ES_SYSTEMS_TMP: Final = RUNTIME_DIR / "es_systems.cfg"
ES_INPUT_CFG: Final = _USER_ES_DIR / "es_input.cfg"
ES_INI_TMP: Final = RUNTIME_DIR / "emulationstation.ini"
ES_INI_CFG: Final = _USER_ES_DIR / "emulationstation.ini"
# The retrobox-emulationstation package installs it in FRONTEND_DIR and links it
# as `retrobox-emulationstation` in the PATH; the PATH name is the fallback when
# it lives elsewhere (e.g. a distro package with another prefix).
ES_EXECUTABLE: Final = (
    FRONTEND_DIR / "emulationstation"
    if (FRONTEND_DIR / "emulationstation").exists()
    else Path(shutil.which("retrobox-emulationstation") or FRONTEND_DIR / "emulationstation")
)

# Recursos de ES y configgen (sistema)
_ES_RESOURCES_DIR: Final = FRONTEND_DIR / "resources"
ES_GUNS_METADATA: Final = _ES_RESOURCES_DIR / "gungames.xml"
ES_WHEELS_METADATA: Final = _ES_RESOURCES_DIR / "wheelgames.xml"
ES_GAMES_METADATA: Final = _ES_RESOURCES_DIR / "gamesdb.xml"
ES_GUNS_ART_METADATA: Final = DEFAULTS_DIR / "data" / "gamesbuttonsdb.xml"
