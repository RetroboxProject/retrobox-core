"""RetroArch's RetroAchievements: the ``cheevos_*`` settings of retroarch.cfg.

EmulationStation's RETROACHIEVEMENTS SETTINGS menu keeps its choices in the
game configuration (``global.`` in its settings file, so a system or a game
can override them like any other option):

=========================================== ====================================
``retroachievements``                       the switch
``retroachievements.username``              the account
``retroachievements.token``                 the login token, which EmulationStation
                                            asks the server for when the account
                                            is validated
``retroachievements.password``              only used when there is no token
``retroachievements.hardcore``              no loading states, rewind or cheats
``retroachievements.leaderboards``          only counts together with hardcore
``retroachievements.verbose``               progress and extra notifications
``retroachievements.richpresence``          what the player is doing, on the site
``retroachievements.encore``                unlocked achievements can be earned again
``retroachievements.screenshot``            screenshot on every unlock
``retroachievements.challenge_indicators``  icons for the achievements in reach
``retroachievements.unofficial``            unofficial achievements too
``retroachievements.sound``                 name of an ``.ogg`` file (no suffix)
                                            of the unlock sound folders
=========================================== ====================================

Every key is written on every launch, enabled or not, so what one game turned
on never leaks into the next one. Whether a core can earn achievements at all
is up to RetroArch; ``cheevos_cores`` of ``share/emu_features/libretro.yaml``
only tells EmulationStation which ones to offer them for.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from retrobox.paths import DATA_DIR

if TYPE_CHECKING:
    from ...config import SystemConfig

_logger = logging.getLogger(__name__)

# The two folders EmulationStation lists the unlock sounds from, the user's
# first (retroachievementsounds= in emulationstation.ini, see es_ini_generator).
USER_SOUNDS_DIR: Final = DATA_DIR / "retroachievements-sounds"
SYSTEM_SOUNDS_DIR: Final = Path("/usr/share/libretro/assets/sounds")
_SOUND_SUFFIX: Final = ".ogg"
_NO_SOUND: Final = "none"

# game configuration switch -> retroarch.cfg setting that follows it as it is
_SWITCHES: Final = {
    "retroachievements.verbose": "cheevos_verbose_enable",
    "retroachievements.richpresence": "cheevos_richpresence_enable",
    "retroachievements.encore": "cheevos_start_active",
    "retroachievements.screenshot": "cheevos_auto_screenshot",
    "retroachievements.challenge_indicators": "cheevos_challenge_indicators",
    "retroachievements.unofficial": "cheevos_test_unofficial",
}

HARDCORE_SETTING: Final = "cheevos_hardcore_mode_enable"

# What a game that does not use achievements gets: everything off.
_DISABLED: Final = {
    "cheevos_enable": "false",
    HARDCORE_SETTING: "false",
    "cheevos_leaderboards_enable": "false",
    "cheevos_unlock_sound_enable": "false",
    **dict.fromkeys(_SWITCHES.values(), "false"),
}


def _bool(value: bool) -> str:
    """A boolean as retroarch.cfg spells it."""
    return "true" if value else "false"


def _quoted(value: str) -> str | None:
    """``value`` as a string setting of retroarch.cfg, or None if it is empty or unwritable.

    The file format has no escape for a double quote or a line break.
    """
    if not value or any(char in value for char in '"\r\n'):
        return None
    return f'"{value}"'


def unlock_sound(name: str) -> Path | None:
    """Find the unlock sound called ``name`` (what EmulationStation stores).

    Args:
        name: The file name without ``.ogg``; ``none`` and the empty string
            mean no sound.

    Returns:
        The file of the user's folder, else of the system one; None if there is
        no sound, if ``name`` is a path (only the listed names are valid) or if
        no folder has it.
    """
    if not name or name == _NO_SOUND or name != Path(name).name:
        return None
    for directory in (USER_SOUNDS_DIR, SYSTEM_SOUNDS_DIR):
        candidate = directory / f"{name}{_SOUND_SUFFIX}"
        if candidate.is_file():
            return candidate
    _logger.warning("RetroAchievements unlock sound '%s' not found, no sound", name)
    return None


def _credentials(config: SystemConfig) -> dict[str, str] | None:
    """The account settings of retroarch.cfg, or None if the account is unusable.

    The token is preferred; the password only logs in when there is none (and
    RetroArch swaps it for a token by itself).
    """
    username = _quoted(config.get_str("retroachievements.username", "").strip())
    token = _quoted(config.get_str("retroachievements.token", "").strip())
    password = _quoted(config.get_str("retroachievements.password", ""))
    if not username:
        _logger.warning("RetroAchievements is on but there is no (valid) username")
        return None
    if token:
        return {
            "cheevos_username": username,
            "cheevos_token": token,
            "cheevos_password": '""',
        }
    if password:
        return {
            "cheevos_username": username,
            "cheevos_token": '""',
            "cheevos_password": password,
        }
    _logger.warning("RetroAchievements is on but there is no (valid) token or password")
    return None


def settings(config: SystemConfig) -> dict[str, str]:
    """The ``cheevos_*`` settings that a game needs.

    Args:
        config: The configuration of the game.

    Returns:
        The settings, always the same keys (see ``_DISABLED``) plus the
        account ones when achievements are on. ``HARDCORE_SETTING`` tells
        whether the game runs in hardcore mode.
    """
    if not config.get_bool("retroachievements"):
        return dict(_DISABLED)
    account = _credentials(config)
    if account is None:
        return dict(_DISABLED)

    # Hardcore mode disables the savestates that netplay is built on.
    hardcore = config.get_bool("retroachievements.hardcore")
    if hardcore and config.get_str("netplay.mode", ""):
        _logger.info("RetroAchievements hardcore mode is off while netplay is on")
        hardcore = False

    result = {
        **_DISABLED,
        **account,
        "cheevos_enable": "true",
        HARDCORE_SETTING: _bool(hardcore),
        # leaderboards need hardcore (EmulationStation says so in its menu)
        "cheevos_leaderboards_enable": _bool(
            hardcore and config.get_bool("retroachievements.leaderboards")
        ),
    }
    for switch, setting in _SWITCHES.items():
        result[setting] = _bool(config.get_bool(switch))

    if sound := unlock_sound(config.get_str("retroachievements.sound", "")):
        result["cheevos_unlock_sound_enable"] = "true"
        result["cheevos_unlock_sound"] = f'"{sound}"'
    return result
