"""RetroArch overlay (bezel) configuration.

Whether a bezel may be drawn at all (``force_no_bezel``, ``bezel``, tattoo and
QR code) is decided by ``configgen.utils.bezel_policy``; this module turns that
decision into RetroArch settings and overlay files.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from retrobox.paths import SHADER_BEZELS_DIR, RUNTIME_DIR

from ...exceptions import RetroboxException
from ...utils import bezels as bezels_util
from ...utils.bezels import GunBorders
from ...utils.bezel_policy import resolve_bezel_settings
from .libretro_ratio import CUSTOM_RATIO_INDEX
from .libretroPaths import RETROARCH_OVERLAY_CONFIG

if TYPE_CHECKING:
    from ...typedefs import Resolution
    from ...Emulator import Emulator
    from ...utils.bezel_policy import BezelSettings
    from ..Generator import Generator

_logger = logging.getLogger(__name__)

_GUN_BEZEL_PNG = RUNTIME_DIR / "bezel_gun_black.png"
_GUN_BEZEL_INFO = RUNTIME_DIR / "bezel_gun_black.info"
_PER_GAME_BEZEL_PNG = RUNTIME_DIR / "bezel_per_game.png"

# below this screen ratio (4:3 and the like) a bezel leaves no room for the game
_MIN_BEZEL_SCREEN_RATIO = 1.6
_VIEWPORT_KEYS = ("width", "height", "top", "left", "bottom", "right")
_FOUR_THIRDS = 4 / 3
_RATIO_EPSILON = 0.01
# fallback bezel borders, expressed over a 1920x1080 picture
_DEFAULT_TOP_BOTTOM = 2 / 1080
_DEFAULT_LEFT_RIGHT = 241 / 1920
_CENTERED = "0.500000"
_NOT_CENTERED = "0.000000"


@dataclass(frozen=True)
class BezelRequest:
    """Everything needed to configure the overlay of one game."""

    generator: Generator
    system: Emulator
    rom: Path
    resolution: Resolution
    bezel: str | None
    shader_bezel: bool
    gun_borders: GunBorders | None


@dataclass
class _Overlay:
    """A bezel image with its parsed info file."""

    png: Path
    specific_to_game: bool
    infos: dict[str, Any]


def _gun_borders_overlay(request: BezelRequest, borders: GunBorders) -> _Overlay:
    """Build a transparent bezel that only reserves room for the gun borders."""
    width = request.resolution["width"]
    height = request.resolution["height"]
    inner_size, outer_size = bezels_util.gun_borders_size(borders.size)
    border = bezels_util.guns_border_size(width, height, inner_size, outer_size)
    ratio = request.generator.getInGameRatio(
        request.system.config, request.resolution, request.rom
    )

    side = border
    if ratio == _FOUR_THIRDS:
        side = (width - (height * _FOUR_THIRDS)) // 2 + border

    infos: dict[str, Any] = {
        "width": width,
        "height": height,
        "top": border,
        "left": side,
        "bottom": border,
        "right": side,
        "opacity": 1.0,
        "messagex": 0.22,
        "messagey": 0.12,
    }
    _GUN_BEZEL_INFO.write_text(json.dumps(infos), encoding="utf-8")
    bezels_util.create_transparent_bezel(_GUN_BEZEL_PNG, width, height)
    return _Overlay(_GUN_BEZEL_PNG, True, infos)


def _find_overlay(request: BezelRequest) -> _Overlay | None:
    """Find the bezel to use, or None when no overlay must be drawn."""
    if request.bezel is None:
        if request.gun_borders is None:
            return None
        return _gun_borders_overlay(request, request.gun_borders)

    found = bezels_util.get_bezel_infos(
        request.rom, request.bezel, request.system.name, "retroarch"
    )
    if found is None:
        return None
    infos = bezels_util.read_bezel_infos(found["info"])
    return _Overlay(found["png"], found["specific_to_game"], infos)


def _needs_adaptation(
    request: BezelRequest,
    overlay: _Overlay,
    viewport_used: bool,
    config: dict[str, object],
) -> bool | None:
    """Tell whether the bezel must be resized to the screen.

    Also fills in the bezel borders when its info file has none.

    Returns:
        True or False, or None when the bezel cannot be used on this screen.
    """
    width = request.resolution["width"]
    height = request.resolution["height"]
    infos = overlay.infos
    too_narrow = width / height < _MIN_BEZEL_SCREEN_RATIO and request.gun_borders is None

    if viewport_used:
        needs_adaptation = (width, height) != (infos["width"], infos["height"])
        if needs_adaptation and too_narrow:
            return None
        config["aspect_ratio_index"] = str(CUSTOM_RATIO_INDEX)
        return needs_adaptation

    if too_narrow:
        return None
    try:
        bezel_width, bezel_height = bezels_util.fast_image_size(overlay.png)
    except (OSError, ValueError):
        _logger.debug("unable to read the size of the bezel %s", overlay.png)
        return None

    infos.update(
        width=bezel_width,
        height=bezel_height,
        top=int(bezel_height * _DEFAULT_TOP_BOTTOM),
        left=int(bezel_width * _DEFAULT_LEFT_RIGHT),
        bottom=int(bezel_height * _DEFAULT_TOP_BOTTOM),
        right=int(bezel_width * _DEFAULT_LEFT_RIGHT),
    )
    return (width, height) != (bezel_width, bezel_height)


def _set_viewport(
    config: dict[str, object], x_pos: int, y_pos: int, width: int, height: int
) -> None:
    """Set the RetroArch custom viewport."""
    config["custom_viewport_x"] = x_pos
    config["custom_viewport_y"] = y_pos
    config["custom_viewport_width"] = width
    config["custom_viewport_height"] = height


def _adapt_overlay_image(
    request: BezelRequest, overlay: _Overlay, settings: BezelSettings, stretch: bool
) -> Path | None:
    """Resize the bezel to the screen and decorate it.

    Returns:
        The final image, or None if the bezel could not be adapted.
    """
    infos = overlay.infos
    if overlay.specific_to_game:
        output_png = _PER_GAME_BEZEL_PNG
    else:
        output_png = Path("/tmp") / f"{overlay.png.stem}_adapted.png"

    # a shared bezel that was already adapted can be reused as it is
    reusable = (
        not overlay.specific_to_game
        and not settings.has_tattoo
        and not settings.has_qrcode
        and output_png.exists()
    )
    if not reusable:
        try:
            bezels_util.pad_image(
                overlay.png,
                output_png,
                request.resolution["width"],
                request.resolution["height"],
                infos["width"],
                infos["height"],
                stretch,
            )
        except (OSError, ValueError, RetroboxException) as err:
            _logger.debug("Failed to create adapted bezel: %s", err)
            return None

    return bezels_util.add_decorations(request.system, output_png, settings)


def _stretched_viewport(
    request: BezelRequest, infos: dict[str, Any], config: dict[str, object]
) -> None:
    """Set the viewport of a bezel stretched to the whole screen."""
    screen_width = request.resolution["width"]
    screen_height = request.resolution["height"]
    width_scale = screen_width / float(infos["width"])
    height_scale = screen_height / float(infos["height"])
    game_ratio = screen_width / float(screen_height)
    viewport_ratio = float(infos["width"]) / float(infos["height"])

    border_x = 0
    if viewport_ratio - game_ratio > _RATIO_EPSILON:
        border_x = (infos["width"] - int(infos["width"] * game_ratio / viewport_ratio)) // 2

    inner_width = infos["width"] - infos["left"] - infos["right"]
    inner_height = infos["height"] - infos["top"] - infos["bottom"]
    _set_viewport(
        config,
        int(round((infos["left"] - border_x / 2) * width_scale)),
        int(round(infos["top"] * height_scale)),
        int(round((inner_width + border_x) * width_scale)),
        int(round(inner_height * height_scale)),
    )


def _padded_viewport(
    request: BezelRequest, infos: dict[str, Any], config: dict[str, object]
) -> None:
    """Set the viewport of a bezel that keeps its ratio and is centered."""
    width_scale = request.resolution["width"] / float(infos["width"])
    height_scale = request.resolution["height"] / float(infos["height"])
    x_offset = request.resolution["width"] - (infos["width"] * width_scale)
    y_offset = request.resolution["height"] - (infos["height"] * height_scale)

    inner_width = infos["width"] - infos["left"] - infos["right"]
    inner_height = infos["height"] - infos["top"] - infos["bottom"]
    _set_viewport(
        config,
        int(round(infos["left"] * width_scale + x_offset / 2)),
        int(round(infos["top"] * height_scale + y_offset / 2)),
        int(round(inner_width * width_scale)),
        int(round(inner_height * height_scale)),
    )


def _write_overlay_cfg(overlay_png: Path) -> None:
    """Write the RetroArch overlay file pointing at the bezel image."""
    RETROARCH_OVERLAY_CONFIG.write_text(
        "overlays = 1\n"
        f'overlay0_overlay = "{overlay_png}"\n'
        "overlay0_full_screen = true\n"
        # RetroArch needs the (empty) list of descriptors, or it ignores the overlay
        "overlay0_descs = 0\n",
        encoding="utf-8",
    )


def _link_shader_bezel(overlay_png: Path) -> None:
    """Expose the bezel to the "noBezel" shaders through a symlink."""
    SHADER_BEZELS_DIR.mkdir(parents=True, exist_ok=True)
    shader_bezel_file = SHADER_BEZELS_DIR / "bezel.png"
    if shader_bezel_file.exists() or shader_bezel_file.is_symlink():
        shader_bezel_file.unlink()
    shader_bezel_file.symlink_to(overlay_png)


def write_bezel_config(request: BezelRequest, config: dict[str, object]) -> None:
    """Configure the RetroArch overlay (bezel and gun borders) for the game.

    Nothing is drawn when the bezel is switched off, unless the gun borders
    need an overlay: ``force_no_bezel`` never removes those.

    Args:
        request: What to configure the overlay for.
        config: The RetroArch settings, updated in place.
    """
    config["input_overlay_hide_in_menu"] = "false"
    config["input_overlay_enable"] = "false"
    config["video_message_pos_x"] = 0.05
    config["video_message_pos_y"] = 0.05

    overlay = _find_overlay(request)
    if overlay is None:
        return

    infos = overlay.infos
    viewport_used = all(key in infos for key in _VIEWPORT_KEYS) and not request.shader_bezel
    adaptation = _needs_adaptation(request, overlay, viewport_used, config)
    if adaptation is None:
        return

    settings = resolve_bezel_settings(request.system.config)
    overlay_png = overlay.png

    if adaptation:
        stretch = request.system.config.get_bool("bezel_stretch")
        if (
            request.resolution["width"] < infos["width"]
            or request.resolution["height"] < infos["height"]
        ):
            stretch = True
        adapted_png = _adapt_overlay_image(request, overlay, settings, stretch)
        if adapted_png is None:
            return
        overlay_png = adapted_png
        if stretch:
            _stretched_viewport(request, infos, config)
        else:
            _padded_viewport(request, infos, config)
    else:
        if viewport_used:
            _set_viewport(
                config,
                infos["left"],
                infos["top"],
                infos["width"] - infos["left"] - infos["right"],
                infos["height"] - infos["top"] - infos["bottom"],
            )
        config["video_message_pos_x"] = infos.get("messagex", 0.0)
        config["video_message_pos_y"] = infos.get("messagey", 0.0)

    # only now that the bezel is usable, so a failure never leaves an overlay on
    if not request.shader_bezel:
        config["input_overlay_enable"] = "true"
    config["input_overlay_scale"] = "1.0"
    config["input_overlay"] = RETROARCH_OVERLAY_CONFIG
    config["input_overlay_hide_in_menu"] = "true"
    config["input_overlay_opacity"] = infos.get("opacity", 1.0)

    centered = config["aspect_ratio_index"] != str(CUSTOM_RATIO_INDEX)
    config["video_viewport_bias_x"] = _CENTERED if centered else _NOT_CENTERED
    config["video_viewport_bias_y"] = _CENTERED if centered else _NOT_CENTERED

    if request.gun_borders is not None:
        overlay_png = bezels_util.add_gun_borders(
            request.system, overlay_png, request.gun_borders
        )

    _write_overlay_cfg(overlay_png)
    if request.shader_bezel:
        _link_shader_bezel(overlay_png)
