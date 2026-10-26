"""Single place that decides whether a bezel may be drawn for a game.

The ``force_no_bezel`` option switches every bezel off for a game, no matter
what ``bezel`` is set to. Because the launcher builds the configuration by
layering several sources, the option can be scoped at any level:

* the option set in a system YAML or in ``defaults.yml`` (per emulator/core);
* ``<system>.force_no_bezel=1`` (a whole console);
* ``<system>.folder["<dir>"].force_no_bezel=1`` (a ROM folder);
* ``<system>["<rom>"].force_no_bezel=1`` (a single game);
* ``global.force_no_bezel=1`` (everything).

A generator that knows its emulator cannot cope with a bezel image (for
example because it forces a stretched or custom aspect ratio) overrides
``Generator.allows_bezel`` instead of writing into the configuration. That
only drops the bezel image: the tattoo, the QR code and the gun borders are
still drawn, as they never depend on the aspect ratio of the game.

Nothing here touches gun borders: switching the bezel off does not remove the
borders a lightgun needs, those follow their own settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Config

_logger = logging.getLogger(__name__)

FORCE_NO_BEZEL_KEY = "force_no_bezel"
NO_BEZEL = "none"
MODE_DISABLED = "0"


@dataclass(frozen=True, slots=True)
class BezelSettings:
    """Effective bezel options of a game, once ``force_no_bezel`` is applied.

    Attributes:
        name: The bezel set to use, or None when no bezel must be drawn.
        tattoo: The tattoo mode, ``"0"`` when disabled.
        qrcode: The RetroAchievements QR code mode, ``"0"`` when disabled.
    """

    name: str | None = None
    tattoo: str = MODE_DISABLED
    qrcode: str = MODE_DISABLED

    @property
    def has_tattoo(self) -> bool:
        """Return True when a tattoo must be drawn on the bezel."""
        return self.tattoo != MODE_DISABLED

    @property
    def has_qrcode(self) -> bool:
        """Return True when the RetroAchievements QR code must be drawn."""
        return self.qrcode != MODE_DISABLED

    @property
    def is_empty(self) -> bool:
        """Return True when there is no bezel, tattoo or QR code to draw."""
        return self.name is None and not self.has_tattoo and not self.has_qrcode


def is_bezel_forced_off(config: Config) -> bool:
    """Return True when ``force_no_bezel`` is enabled for the current game."""
    return config.get_bool(FORCE_NO_BEZEL_KEY)


def configured_bezel(config: Config) -> str | None:
    """Return the bezel set to use, or None when no bezel must be drawn.

    ``None`` is returned both when ``force_no_bezel`` is on and when the
    ``bezel`` option is unset, empty or ``"none"``.
    """
    if is_bezel_forced_off(config):
        return None

    name = config.get_str("bezel", NO_BEZEL)
    if name in ("", NO_BEZEL):
        return None
    return name


def _flag(config: Config, key: str) -> str:
    """Return a mode option as a string, with an empty value meaning disabled."""
    return config.get_str(key, MODE_DISABLED) or MODE_DISABLED


def resolve_bezel_settings(config: Config, *, bezel_allowed: bool = True) -> BezelSettings:
    """Return the bezel, tattoo and QR code options to apply to the game.

    Args:
        config: The configuration of the running game.
        bezel_allowed: False when the emulator cannot use a bezel image (see
            ``Generator.allows_bezel``); the tattoo and the QR code stay.

    Returns:
        The effective options. Everything is switched off when
        ``force_no_bezel`` is on.
    """
    if is_bezel_forced_off(config):
        _logger.debug("bezel, tattoo and qrcode disabled by %s", FORCE_NO_BEZEL_KEY)
        return BezelSettings()

    return BezelSettings(
        name=configured_bezel(config) if bezel_allowed else None,
        tattoo=_flag(config, "bezel.tattoo"),
        qrcode=_flag(config, "bezel.qrcode"),
    )
