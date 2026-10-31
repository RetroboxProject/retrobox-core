"""Module for handling emulationstation.ini generation."""
import logging
from pathlib import Path

from retrobox.configgen.utils.logger import OK
from retrobox.configgen.generators.libretro.libretroPaths import (
    _RETROARCH_AUDIO_FILTERS,
    _RETROARCH_VIDEO_FILTERS
)

from retrobox.paths import (
    mkdir_if_not_exists,
    _DECORATIONS_DEF_DIR,
    _DECORATIONS_DIR,
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
    _SHADERS_DIR,
    DATA_DIR,
    ES_INI_CFG,
    ES_INI_TMP,
    LOGS,
    MUSIC_DIR,
    SAVES,
    SCREENSHOTS,
    FRONTEND_DIR,
    THEMES_DIR,
)

_logger = logging.getLogger(__name__)


INI_CONTENT = f"""
# ROOT AND LOGS
root={DATA_DIR}
log={LOGS}

# SAVES
saves={SAVES}

# SCREENSHOTS
screenshots={SCREENSHOTS}

# THEMES: shipped with the install (read-only) and user-installed
system.themes={FRONTEND_DIR}/themes
themes={THEMES_DIR}

# BACKGROUND MUSIC FOR MENUS
music={MUSIC_DIR}

# DECORATIONS/BEZELS
system.decorations={_DECORATIONS_DEF_DIR}
decorations={_DECORATIONS_DIR}

# RETROARCH SHADERS
shaders={_SHADERS_DIR}/configs

# RETROARCH VIDEO FILTERS
videofilters={_RETROARCH_VIDEO_FILTERS}

# RETROARCH AUDIO FILTERS
audiofilters={_RETROARCH_AUDIO_FILTERS}

# RETROACHIEVEMENT SOUNDS
retroachievementsounds={DATA_DIR}/retroachievements-sounds

# PAD-TO-KEYBOARD (gamepadly) MAPPINGS
system.padtokey={_GAMEPADLY_PROFILES}
padtokey={_GAMEPADLY_USER_PROFILES}

# TIMEZONES
timezones=/usr/share/zoneinfo
"""

def ensure_ini_directories() -> None:
    """
    Create the user-writable directories referenced by emulationstation.ini.

    EmulationStation only honours a key of that file if the directory it
    points at already exists (Paths::loadCustomConfiguration checks
    isDirectory() and silently ignores the key otherwise), so they must be
    created BEFORE the frontend starts. Directories owned by an installer
    (RetroArch filters, system defaults) are deliberately not created here.
    """
    for directory in (
        _DECORATIONS_DIR,
        LOGS,
        SAVES,
        SCREENSHOTS,
        MUSIC_DIR,
        THEMES_DIR,
        _SHADERS_DIR / "configs",
        _GAMEPADLY_USER_PROFILES,
    ):
        mkdir_if_not_exists(directory)


def generate_emulationstation_ini(output_path: Path = ES_INI_TMP):
    """
    Generates emulationstation.ini for directory mappings to some retrobox resources.
    """

    _logger.debug("Generating %s", output_path)

    if output_path.exists():
        output_path.unlink()

    try:
        output_path.write_text(INI_CONTENT, encoding="utf-8")
        _logger.log(OK, "Generated %s", output_path.name)
    except OSError as e:
        _logger.error("Couldn't write %s: %s", output_path, e)
        raise

    if output_path != ES_INI_CFG:
        try:
            if ES_INI_CFG.exists() or ES_INI_CFG.is_symlink():
                ES_INI_CFG.unlink()
            ES_INI_CFG.symlink_to(output_path)
            _logger.debug("Linked %s -> %s", ES_INI_CFG, output_path)
        except FileNotFoundError:
            _logger.error(
                "Can't create symlink in %s",
                ES_INI_CFG.parent
            )
            raise
        except OSError as e:
            _logger.error("Failed to link %s -> %s: %s", ES_INI_CFG, output_path, e)
            raise
