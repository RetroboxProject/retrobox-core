"""Gun help image and internal gun borders, both best effort."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from retrobox.configgen.utils import bezels as bezels_util
from retrobox.paths import GUN_OVERLAYS_DIR

if TYPE_CHECKING:
    from .session import GameSession

_logger = logging.getLogger(__name__)


def generate_gun_help(session: GameSession) -> None:
    """Generate the gun help image, never failing the launch."""
    system = session.system
    try:
        bezels_util.generate_gun_help(
            session.args.system,
            session.rom,
            system.config.use_guns,
            session.inputs.guns,
            GUN_OVERLAYS_DIR,
            "gun_help.png",
            session.resolution,
        )
    except Exception as err:  # pylint: disable=broad-exception-caught
        # best effort: a missing gun help must never prevent the game from starting
        _logger.error("Failed to generate the gun help image")
        _logger.error(err)


def draw_internal_gun_borders(session: GameSession) -> None:
    """Draw the configgen internal gun borders if needed, never failing the launch."""
    system = session.system
    guns = session.inputs.guns
    try:
        if not (system.config.use_guns and guns):
            return

        if session.generator.supportsInternalBezels() or system.config.get_bool("hud_support"):
            _logger.debug(
                "skipping configgen internal gun borders for emulator %s", system.config.emulator
            )
            return

        gun_border_size_name = system.guns_borders_size_name(guns)
        if gun_border_size_name is None:
            return

        _logger.debug(
            "using configgen internal gun borders for emulator %s", system.config.emulator
        )
        # pylint: disable-next=import-outside-toplevel
        from retrobox.configgen.utils.gun_borders import draw_gun_borders

        draw_gun_borders(
            gun_border_size_name,
            bezels_util.guns_borders_color_from_config(system.config),
            system.guns_border_ratio_type(guns),
        )
    except Exception as err:  # pylint: disable=broad-exception-caught
        # best effort: missing gun borders must never prevent the game from starting
        _logger.error("Failed to draw_gun_borders for gun_borders")
        _logger.error(err)
