"""Build the bezel image that MangoHud draws as its background.

Whether a bezel may be drawn at all is decided by
``configgen.utils.bezel_policy`` (``force_no_bezel`` and friends); this module
only builds the image once that decision is taken.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from configgen.exceptions import RetroboxException
from configgen.utils import bezels as bezels_util
from configgen.utils.bezel_policy import resolve_bezel_settings

if TYPE_CHECKING:
    from configgen.batoceraTypes import Resolution
    from configgen.Emulator import Emulator
    from configgen.generators.Generator import Generator
    from configgen.gun import Guns

_logger = logging.getLogger(__name__)

# Bezels cover the whole target resolution. If the bezel aspect ratio does not
# match the screen one, it is stretched by default, instead of being rejected or
# padded with black; the "bezel_stretch" option of the game can turn that off.
_DEFAULT_BEZEL_STRETCH = True
# max cover proportion and ratio distortion (only used when not stretching)
_MAX_COVER = 0.05  # 5%
_MAX_RATIO_DELTA = 0.01

_TRANSPARENT_BEZEL_PNG = Path("/tmp/bezel_transhud_black.png")
_TRANSPARENT_BEZEL_INFO = Path("/tmp/bezel_transhud_black.info")
_RESIZED_BEZEL_PNG = Path("/tmp/bezel.png")
_RESIZED_BEZEL_INFO = Path("/tmp/bezel.info")


@dataclass
class _Overlay:
    """A bezel image with its info file and the parsed info."""

    png: Path
    info_file: Path
    infos: dict[str, Any]


def _load_overlay(
    system: Emulator, rom: Path, resolution: Resolution, bezel: str | None
) -> _Overlay | None:
    """Find the bezel to use (or generate a transparent one) and read its info."""
    if bezel is None:
        # no bezel: generate a transparent one for the tattoo/gun borders and so on
        png_file = _TRANSPARENT_BEZEL_PNG
        info_file = _TRANSPARENT_BEZEL_INFO
        width = resolution["width"]
        height = resolution["height"]
        bezels_util.create_transparent_bezel(png_file, width, height)
        info_file.write_text(
            f'{{ "width":{width}, "height":{height}, "opacity":1.0000000, '
            '"messagex":0.220000, "messagey":0.120000 }',
            encoding="utf-8",
        )
    else:
        _logger.debug("hud enabled. trying to apply the bezel %s", bezel)

        bezel_infos = bezels_util.get_bezel_infos(rom, bezel, system.name, system.config.emulator)
        if bezel_infos is None:
            _logger.debug("no bezel info file found")
            return None

        info_file = bezel_infos["info"]
        png_file = bezel_infos["png"]

    return _Overlay(png_file, info_file, bezels_util.read_bezel_infos(info_file))


def _bezel_size(overlay: _Overlay) -> tuple[int, int]:
    """Return the bezel size, from its info file if possible, else from the PNG."""
    if "width" in overlay.infos and "height" in overlay.infos:
        _logger.info("bezel size read from %s", overlay.info_file)
        return overlay.infos["width"], overlay.infos["height"]
    _logger.info("bezel size read from %s", overlay.png)
    return bezels_util.fast_image_size(overlay.png)


def _bezel_fits(
    infos: dict[str, Any],
    bezel_size: tuple[int, int],
    resolution: Resolution,
    ingame_ratio: float,
) -> bool:
    """Check that the bezel is compatible with the screen and the in-game image.

    Only used when the bezel is not stretched: the screen and bezel ratios must
    be approximately the same, and bottom, top, left and right must not cover
    too much of the game image.
    """
    bezel_width, bezel_height = bezel_size
    screen_ratio = resolution["width"] / resolution["height"]
    bezel_ratio = bezel_width / bezel_height

    if abs(screen_ratio - bezel_ratio) > _MAX_RATIO_DELTA:
        _logger.debug(
            "screen ratio (%s) is too far from the bezel one (%s) : delta > %s",
            screen_ratio,
            bezel_ratio,
            _MAX_RATIO_DELTA,
        )
        return False

    # the bezel top and bottom cover must be minimum
    # (if there is no information about top/bottom, assume default is 0)
    for side in ("top", "bottom"):
        if side in infos and infos[side] / bezel_height > _MAX_COVER:
            _logger.debug(
                "bezel %s covers too much the game image : %s / %s > %s",
                side,
                infos[side],
                bezel_height,
                _MAX_COVER,
            )
            return False

    # the bezel left and right cover must be maximum
    img_width = bezel_height * ingame_ratio
    margin = (bezel_width - img_width) / 2.0
    # assume default is 4/3 over 16/9
    default_side = (bezel_width - (bezel_height / 3 * 4)) / 2
    for side in ("left", "right"):
        delta = infos.get(side, default_side) - margin
        if abs(delta / img_width) > _MAX_COVER:
            _logger.debug(
                "bezel %s covers too much the game image : %s / %s > %s",
                side,
                delta,
                img_width,
                _MAX_COVER,
            )
            return False
    return True


def _resize_bezel(
    overlay: _Overlay, bezel_size: tuple[int, int], resolution: Resolution, stretch: bool
) -> Path | None:
    """Resize the bezel (and its info file) to the screen resolution."""
    _logger.debug("bezel needs to be resized")
    width = resolution["width"]
    height = resolution["height"]
    try:
        bezels_util.resize_image(overlay.png, _RESIZED_BEZEL_PNG, width, height, stretch)

        # The PNG has been stretched independently in X/Y. The sidecar .info
        # must receive the same transformation so the game's opening stays
        # aligned with the transparent opening in the bezel.
        if overlay.info_file.exists():
            bezels_util.resize_info(
                overlay.info_file,
                _RESIZED_BEZEL_INFO,
                bezel_size[0],
                bezel_size[1],
                width,
                height,
                keep_aspect_ratio=not stretch,
            )
    except (OSError, ValueError, RetroboxException) as err:
        _logger.error("failed to resize the image %s", err)
        return None
    return _RESIZED_BEZEL_PNG


def get_hud_bezel(
    system: Emulator,
    generator: Generator,
    rom: Path,
    game_resolution: Resolution,
    guns: Guns,
) -> Path | None:
    """Build the bezel image used as MangoHud background.

    Switching the bezel off with ``force_no_bezel`` does not remove the gun
    borders: if the guns need them, a transparent bezel carrying only the
    borders is still produced.

    Returns:
        The path of the final bezel image, or None if no bezel must be drawn.
    """
    if generator.supportsInternalBezels():
        _logger.debug("skipping bezels for emulator %s", system.config.emulator)
        return None

    settings = resolve_bezel_settings(
        system.config, bezel_allowed=generator.allows_bezel(system.config)
    )
    gun_borders = bezels_util.gun_borders_for(system, guns)

    # no good reason for a bezel
    if settings.is_empty and gun_borders is None:
        return None

    overlay = _load_overlay(system, rom, game_resolution, settings.name)
    if overlay is None:
        return None

    bezel_size = _bezel_size(overlay)
    stretch = system.config.get_bool("bezel_stretch", _DEFAULT_BEZEL_STRETCH)

    # in case there are gun borders, skip the compatibility checks
    if not stretch and gun_borders is None:
        ingame_ratio = generator.getInGameRatio(system.config, game_resolution, rom)
        if not _bezel_fits(overlay.infos, bezel_size, game_resolution, ingame_ratio):
            return None

    overlay_png = overlay.png
    # if screen and bezel sizes don't match, resize
    if bezel_size != (game_resolution["width"], game_resolution["height"]):
        overlay_png = _resize_bezel(overlay, bezel_size, game_resolution, stretch)
        if overlay_png is None:
            return None

    overlay_png = bezels_util.add_decorations(system, overlay_png, settings)
    if gun_borders is not None:
        overlay_png = bezels_util.add_gun_borders(system, overlay_png, gun_borders)

    _logger.debug("applying bezel %s", overlay_png)
    return overlay_png
