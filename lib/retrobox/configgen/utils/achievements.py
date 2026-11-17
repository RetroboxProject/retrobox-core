"""RetroAchievements: the account and the choices of EmulationStation's menu.

EmulationStation's RETROACHIEVEMENTS SETTINGS menu keeps them in the game
configuration (see ``generators/libretro/libretro_achievements.py`` for the
keys). This module reads them once for every emulator that earns achievements
(RetroArch, PCSX2, Dolphin) and for the overlay's achievements page.

The login token is what EmulationStation gets from the server when the
account is validated. RetroArch can still log in with a password; the
standalone emulators can't, so ``login_token()`` swaps a password for a token
on the spot (rcheevos' ``login2`` request) when there is no token.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from retrobox.paths import RETROBOX_ROOTDIR

if TYPE_CHECKING:
    from ..config import SystemConfig

_logger = logging.getLogger(__name__)

SERVER: Final = "https://retroachievements.org/dorequest.php"
_TIMEOUT_SECONDS: Final = 5.0
_NO_SOUND: Final = "none"


@dataclass(frozen=True)
class Account:
    """A RetroAchievements account: a user and a token, or else a password."""

    username: str
    token: str = ""
    password: str = ""

    def for_session(self) -> dict[str, str]:
        """What session.json carries for the overlay: the token, or else the password."""
        if self.token:
            return {"username": self.username, "token": self.token}
        return {"username": self.username, "password": self.password}


@dataclass(frozen=True)
class Options:  # pylint: disable=too-many-instance-attributes  # one per menu entry
    """The switches of EmulationStation's menu, as they apply to one game."""

    hardcore: bool = False
    leaderboards: bool = False
    verbose: bool = False
    richpresence: bool = False
    encore: bool = False
    screenshot: bool = False
    challenge_indicators: bool = False
    unofficial: bool = False
    sound: str = ""

    @property
    def has_sound(self) -> bool:
        """Whether an unlock sound was picked."""
        return bool(self.sound) and self.sound != _NO_SOUND


def enabled(config: SystemConfig) -> bool:
    """Whether achievements are on for the game."""
    return config.get_bool("retroachievements")


def account(config: SystemConfig) -> Account | None:
    """The account of the game configuration.

    Returns:
        The account; None when achievements are off, or there is no user, or
        neither a token nor a password.
    """
    if not enabled(config):
        return None
    username = config.get_str("retroachievements.username", "").strip()
    token = config.get_str("retroachievements.token", "").strip()
    password = config.get_str("retroachievements.password", "")
    if not username or not (token or password):
        return None
    return Account(username, token, "" if token else password)


def session_account(config: SystemConfig) -> dict[str, str] | None:
    """The account the overlay shows the game's achievements with (session.json)."""
    found = account(config)
    return found.for_session() if found else None


def options(config: SystemConfig) -> Options:
    """The menu's switches for the game.

    Hardcore mode is off while netplay is on (it disables the savestates
    netplay is built on), and leaderboards only count together with it.
    """
    hardcore = config.get_bool("retroachievements.hardcore")
    if hardcore and config.get_str("netplay.mode", ""):
        _logger.info("RetroAchievements hardcore mode is off while netplay is on")
        hardcore = False
    return Options(
        hardcore=hardcore,
        leaderboards=hardcore and config.get_bool("retroachievements.leaderboards"),
        verbose=config.get_bool("retroachievements.verbose"),
        richpresence=config.get_bool("retroachievements.richpresence"),
        encore=config.get_bool("retroachievements.encore"),
        screenshot=config.get_bool("retroachievements.screenshot"),
        challenge_indicators=config.get_bool("retroachievements.challenge_indicators"),
        unofficial=config.get_bool("retroachievements.unofficial"),
        sound=config.get_str("retroachievements.sound", ""),
    )


def _user_agent() -> str:
    """Who asks, as the server wants to know (``Retrobox/<version>``)."""
    version_file = RETROBOX_ROOTDIR / "VERSION"
    try:
        version = version_file.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        version = "dev"
    return f"Retrobox/{version}"


def login_token(found: Account, timeout: float = _TIMEOUT_SECONDS) -> str | None:
    """The account's token: its own, or one the server gives for its password.

    Args:
        found: The account.
        timeout: Seconds to wait for the server.

    Returns:
        The token; None when the server can't be reached or refuses the
        password (the reason is logged).
    """
    if found.token:
        return found.token
    body = urllib.parse.urlencode(
        {"r": "login2", "u": found.username, "p": found.password}
    ).encode()
    request = urllib.request.Request(
        SERVER, data=body, headers={"User-Agent": _user_agent()}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            reply = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
        _logger.warning("RetroAchievements: cannot log in as %s: %s", found.username, err)
        return None
    token = reply.get("Token") if isinstance(reply, dict) else None
    if not reply.get("Success") or not isinstance(token, str) or not token:
        reason = reply.get("Error", "no token in the reply") if isinstance(reply, dict) else reply
        _logger.warning("RetroAchievements: login of %s refused: %s", found.username, reason)
        return None
    return token
