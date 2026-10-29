"""Bezel helpers: lookup, resizing, QR codes and tattoos."""

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, cast

import qrcode
from PIL import Image, ImageOps

from retrobox.configgen.utils.language import _detect_language
from retrobox.paths import (
    RUNTIME_DIR,
    _DECORATIONS_DEF_DIR,
    _DECORATIONS_DIR,
    SHARE_DIR,
)
from ..exceptions import RetroboxException
from .videoMode import get_alt_decoration

if TYPE_CHECKING:
    from qrcode.image.pil import PilImage

    from ..Emulator import Emulator
    from .bezel_policy import BezelSettings

_logger = logging.getLogger(__name__)

_TATTOOED_BEZEL_PNG = RUNTIME_DIR / "bezel_tattooed.png"
_QRCODE_BEZEL_PNG = RUNTIME_DIR / "bezel_qrcode.png"


class BezelInfos(TypedDict):
    """Paths describing one bezel candidate."""

    png: Path
    info: Path
    layout: Path
    mamezip: Path
    specific_to_game: bool


def _build(
    directory: Path, basename: str, specific_to_game: bool, locale: str = ""
) -> BezelInfos:
    """Build the file set of a bezel candidate."""
    return {
        "png": directory / f"{basename}{locale}.png",
        "info": directory / f"{basename}.info",
        "layout": directory / f"{basename}.lay",
        "mamezip": directory / f"{basename}.zip",
        "specific_to_game": specific_to_game,
    }


def _candidates_for_root(
    root: Path, rom_base: str, system_name: str, alt_decoration: str, localized: bool
) -> list[BezelInfos]:
    """List bezel candidates under one decorations root, in priority order."""
    games_dir = root / "games"
    systems_dir = root / "systems"
    result = [
        _build(games_dir / system_name, rom_base, True),
        _build(games_dir, rom_base, True),
    ]
    if alt_decoration != "0":
        result.append(_build(systems_dir, f"{system_name}-{alt_decoration}", False))
    if localized:
        result.append(_build(systems_dir, system_name, False, f"_{_detect_language()}"))
    result.append(_build(systems_dir, system_name, False))
    if alt_decoration != "0":
        result.append(_build(root, f"default-{alt_decoration}", True))
    result.append(_build(root, "default", True))
    return result


def get_bezel_infos(
    rom: str | Path,
    bezel: str,
    system_name: str,
    emulator: str,
) -> BezelInfos | None:
    """Obtain bezel info based on this search order for decoration files.

    Within each root (user decorations first, then the default ones):
    #1. rom name inside games/<systemName>/          -> specific to this game
    #2. rom name inside games/                        -> specific to this game
    #3. systemName + alt decoration inside systems/   -> only if altDecoration != "0"
    #4. systemName inside systems/ (localized)        -> user decorations only
    #5. systemName inside systems/
    #6. "default" + alt decoration                    -> only if altDecoration != "0"
    #7. "default"
    The first one to be found wins; if none exist, return None. Whether a bezel
    may be drawn at all (``force_no_bezel``) is decided by the caller through
    ``configgen.utils.bezel_policy``.
    mamezip files are for MAME-specific advanced artwork
    (bezels with overlays and backdrops, animated LEDs, etc.)
    """
    alt_decoration = str(get_alt_decoration(system_name, rom, emulator))
    rom_base = Path(rom).stem  # filename without extension

    # user-provided bezels in the bezels dir ($RETROBOX_DATADIR/decorations), then
    # the RetroBat defaults ($RETROBOX_DATADIR/decorations-default, see
    # tools/decorations/retrobat-bezels.sh)
    candidates = _candidates_for_root(
        Path(_DECORATIONS_DIR) / bezel, rom_base, system_name, alt_decoration, True
    ) + _candidates_for_root(
        Path(_DECORATIONS_DEF_DIR) / bezel, rom_base, system_name, alt_decoration, False
    )

    for candidate in candidates:
        if candidate["png"].exists():
            _logger.debug("Original bezel file used: %s", candidate["png"])
            return candidate

    return None


def read_bezel_infos(info_file: Path) -> dict[str, Any]:
    """Read a bezel info file, returning an empty dict if missing or unreadable."""
    if not info_file.exists():
        return {}
    try:
        with info_file.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        _logger.warning("unable to read the bezel info file %s", info_file)
        return {}


def fast_image_size(image_file: str | Path) -> tuple[int, int]:
    """Read the size of a PNG from its header (much faster than PIL Image.size)."""
    image_path = Path(image_file)
    if not image_path.exists():
        return -1, -1
    with image_path.open("rb") as handle:
        head = handle.read(32)
    if len(head) != 32:
        # corrupted header, or not a PNG
        return -1, -1
    check = struct.unpack(">i", head[4:8])[0]
    if check != 0x0D0A1A0A:
        # not a PNG
        return -1, -1
    return struct.unpack(">ii", head[16:24])  # image width, height


def resize_image(
    input_png: str | Path,
    output_png: str | Path,
    screen_width: int,
    screen_height: int,
    bezel_stretch: bool = False,
) -> None:
    """Resize a bezel to the screen size, stretching it if requested.

    Stretching distorts the aspect ratio if needed, but guarantees that the
    bezel (and its transparent hole) fills the whole screen with no black
    padding and no cropping.
    """
    screen_size = (screen_width, screen_height)
    with Image.open(input_png) as imgin:
        _logger.debug("Resizing bezel: image mode %s, stretch=%s", imgin.mode, bezel_stretch)
        if not bezel_stretch and imgin.mode != "RGBA":
            alpha_paste(input_png, output_png, "black", screen_size, bezel_stretch)
            return
        imgout = imgin.resize(screen_size, Image.Resampling.BICUBIC)
        if bezel_stretch:
            imgout = imgout.convert("RGBA")
        imgout.save(output_png, format="PNG")


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def pad_image(
    input_png: str | Path,
    output_png: str | Path,
    screen_width: int,
    screen_height: int,
    bezel_width: int,  # pylint: disable=unused-argument
    bezel_height: int,  # pylint: disable=unused-argument
    bezel_stretch: bool = False,
) -> None:
    """Pad (or stretch) a bezel to the screen size.

    ``bezel_width`` and ``bezel_height`` are unused and only kept so the
    signature stays compatible with existing callers.
    """
    screen_size = (screen_width, screen_height)
    with Image.open(input_png) as imgin:
        _logger.debug("Padding bezel: image mode %s", imgin.mode)
        if imgin.mode != "RGBA":
            alpha_paste(input_png, output_png, "black", screen_size, bezel_stretch)
            return
        if bezel_stretch:
            # stretch instead of fit (crops) or pad (fills with black)
            imgout = imgin.resize(screen_size, Image.Resampling.BICUBIC)
        else:
            imgout = ImageOps.pad(imgin, screen_size, color="black", centering=(0.5, 0.5))
        imgout.save(output_png, format="PNG")


# pylint: disable-next=too-many-arguments,too-many-positional-arguments,too-many-locals
def resize_info(
    input_info: str | Path,
    output_info: str | Path,
    orig_width: int,
    orig_height: int,
    new_width: int,
    new_height: int,
    keep_aspect_ratio: bool = True,
) -> None:
    """Rescale the geometry fields of a bezel .info file.

    The fields (width, height, top, left, bottom, right) are rescaled so the
    transparent hole stays aligned with the PNG after going from
    (orig_width, orig_height) to (new_width, new_height).

    ``keep_aspect_ratio`` must reflect the transformation applied to the PNG:

    - True: the PNG was stretched independently on each axis (resize_image or
      pad_image with bezel_stretch=True), so top/bottom use the vertical ratio
      and left/right/width use the horizontal one.
    - False: the PNG kept its proportions and was centered on the target
      canvas (bezel_stretch=False, via ImageOps.pad), so a single uniform
      ratio is used and the centering margin is added to left/right/top/bottom.

    If the .info cannot be read, or the original size is invalid, nothing is
    done. This is not fatal: the caller already checks that the file exists.
    """
    input_path = Path(input_info)
    output_path = Path(output_info)

    try:
        with input_path.open(encoding="utf-8") as file:
            infos: dict[str, Any] = json.load(file)
    except (OSError, ValueError) as err:
        _logger.warning("resize_info: could not read %s (%s)", input_path, err)
        return

    if not orig_width or not orig_height:
        _logger.warning("resize_info: invalid source size %sx%s", orig_width, orig_height)
        return

    wratio = new_width / float(orig_width)
    hratio = new_height / float(orig_height)

    if keep_aspect_ratio:
        xratio, yratio = wratio, hratio
        xoffset = yoffset = 0.0
    else:
        xratio = yratio = min(wratio, hratio)
        xoffset = (new_width - orig_width * xratio) / 2.0
        yoffset = (new_height - orig_height * yratio) / 2.0

    # field -> (ratio, offset)
    transforms = {
        "width": (xratio, 0.0),
        "height": (yratio, 0.0),
        "left": (xratio, xoffset),
        "right": (xratio, xoffset),
        "top": (yratio, yoffset),
        "bottom": (yratio, yoffset),
    }
    for key, (ratio, offset) in transforms.items():
        if key in infos:
            infos[key] = round(infos[key] * ratio + offset)

    try:
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(infos, file)
    except OSError as err:
        _logger.warning("resize_info: could not write %s (%s)", output_path, err)


# pylint: disable-next=too-many-locals
def add_qr_code(
    input_png: str | Path, output_png: str | Path, code: str, system: Emulator
) -> None:
    """Paste a RetroAchievements QR code in a corner of the bezel."""
    box_size = 3
    border = 2
    qr_code = qrcode.QRCode(version=1, box_size=box_size, border=border)
    qr_code.add_data(f"https://retroachievements.org/game/{code}")
    qr_code.make()
    qr_image = cast("PilImage", qr_code.make_image(back_color=(120, 120, 120)))
    qr_image = cast("Image.Image", qr_image.convert("RGBA"))

    side = 29 * box_size + border * box_size * 2

    with Image.open(input_png) as bezel_file:
        new_bezel = bezel_file.convert("RGBA")
    width, height = new_bezel.size

    corner = system.config.get("bezel.qrcode_corner", "NE").upper()
    positions = {
        "NW": (0, 0),
        "SE": (width - side, height - side),
        "SW": (0, height - side),
    }
    left, top = positions.get(corner, (width - side, 0))  # default = NE
    new_bezel.paste(qr_image, (left, top, left + side, top + side))
    new_bezel.save(output_png)


def _tattoo_path(system: Emulator) -> Path:
    """Choose which tattoo file to use for this system."""
    overlays = SHARE_DIR / "controller-overlays"
    mode = system.config["bezel.tattoo"]
    if mode == "system":
        path = overlays / f"{system.name}.png"
        return path if path.exists() else overlays / "generic.png"
    if mode == "custom":
        custom = Path(system.config["bezel.tattoo_file"])
        if custom.exists():
            return custom
    return overlays / "generic.png"


def _open_tattoo(path: Path) -> Image.Image:
    """Open a tattoo image as RGBA, raising RetroboxException on failure."""
    try:
        with Image.open(path) as tattoo_file:
            return tattoo_file.convert("RGBA")
    except (OSError, ValueError) as err:
        _logger.error("Error opening tattoo image: %s", path)
        raise RetroboxException(f"Tattoo image could not be opened: {path}") from err


def _scale_tattoo(
    tattoo: Image.Image, bezel_size: tuple[int, int], resize: bool
) -> Image.Image:
    """Scale the tattoo to fit the bezel."""
    bezel_width, bezel_height = bezel_size
    tattoo_width, tattoo_height = tattoo.size
    if resize:
        # slightly smaller than the bezel's column
        new_width = int((225 / 1920) * bezel_width)
    elif tattoo_width > bezel_width or tattoo_height > bezel_height:
        # too large: limit the width to that of the bezel
        new_width = bezel_width
    else:
        return tattoo
    new_height = int(tattoo_height * new_width / tattoo_width)
    return tattoo.resize((new_width, new_height), Image.Resampling.BICUBIC)


def tattoo_image(input_png: Path, output_png: Path, system: Emulator) -> None:
    """Overlay a tattoo (controller image) in a corner of the bezel."""
    tattoo = _open_tattoo(_tattoo_path(system))
    with Image.open(input_png) as bezel_file:
        back = bezel_file.convert("RGBA")
    width, height = back.size
    tattoo = _scale_tattoo(tattoo, back.size, system.config.get_bool("bezel.resize_tattoo", True))
    tattoo_width, tattoo_height = tattoo.size

    # margin for the tattoo (20 pixels vertical on 1080p)
    margin = int((20 / 1080) * height)
    corner = system.config.get("bezel.tattoo_corner", "NW").upper()
    positions = {
        "NE": (width - tattoo_width, margin),
        "SE": (width - tattoo_width, height - tattoo_height - margin),
        "SW": (0, height - tattoo_height - margin),
    }
    # the canvas must be the same size as the bezel for compositing
    canvas = Image.new("RGBA", back.size)
    canvas.paste(tattoo, positions.get(corner, (0, margin)))  # default = NW
    Image.alpha_composite(back, canvas).save(output_png, format="PNG")


def _pad_alpha(alpha: Image.Image, screensize: tuple[int, int], fillcolor: str) -> Image.Image:
    """Pad an alpha channel to the screen size, cropping the sides if needed."""
    img_width, img_height = alpha.size
    screen_width, screen_height = screensize
    img_ratio = img_width / img_height
    screen_ratio = screen_width / screen_height

    if img_ratio - screen_ratio > 0.01:
        # cut off bezel sides for 16:10 screens
        new_width = int(img_width * screen_ratio / img_ratio)
        border = (img_width - new_width) // 2
        alpha = alpha.crop((border, 0, new_width + border, img_height))
        img_width = new_width

    base = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 255))
    base.paste(alpha, (0, 0, img_width, img_height))
    return ImageOps.pad(base, screensize, color=fillcolor, centering=(0.5, 0.5))


def alpha_paste(
    input_png: str | Path,
    output_png: str | Path,
    fillcolor: str,
    screensize: tuple[int, int],
    bezel_stretch: bool,
) -> None:
    """Rebuild a palette+alpha bezel as RGBA at the screen size.

    TheBezelProject bezels are Palette + alpha, not RGBA. PIL cannot convert
    from P+A to RGBA, and cannot save P+A as PNG, so a new image is created.
    """
    with Image.open(input_png) as imgin:
        if "transparency" not in imgin.info:
            raise RetroboxException("No transparent pixels in the bezel image")
        alpha = imgin.split()[-1]  # alpha from the original palette + alpha

    if bezel_stretch:
        # stretch the alpha channel to the exact screen size
        # (avoid ImageOps.fit, which crops, and ImageOps.pad, which fills with black)
        imgout = Image.new("RGBA", screensize, (0, 0, 0, 255))
        imgout.putalpha(alpha.resize(screensize, Image.Resampling.BICUBIC))
    else:
        imgout = _pad_alpha(alpha, screensize, fillcolor)

    imgout.save(output_png, format="PNG")


def create_transparent_bezel(output_png: Path, width: int, height: int) -> None:
    """Create a fully transparent bezel image."""
    Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(output_png, format="PNG")


def add_decorations(system: Emulator, input_png: Path, settings: BezelSettings) -> Path:
    """Add the tattoo and the RetroAchievements QR code to a bezel, if enabled.

    Args:
        system: The running system.
        input_png: The bezel image to decorate.
        settings: The effective bezel options (see ``bezel_policy``).

    Returns:
        The decorated image, or ``input_png`` itself when nothing was added.
    """
    output_png = input_png
    if settings.has_tattoo:
        tattoo_image(output_png, _TATTOOED_BEZEL_PNG, system)
        output_png = _TATTOOED_BEZEL_PNG

    if (
        settings.has_qrcode
        and (cheevos_id := system.es_game_info.get("cheevosId", "0")) != "0"
    ):
        add_qr_code(output_png, _QRCODE_BEZEL_PNG, cheevos_id, system)
        output_png = _QRCODE_BEZEL_PNG

    return output_png


