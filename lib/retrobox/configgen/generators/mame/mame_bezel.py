"""MAME artwork (bezel) configuration.

Whether a bezel may be drawn at all (``force_no_bezel``, ``bezel``, tattoo and
QR code) is decided by ``configgen.utils.bezel_policy``; this module turns that
decision into the artwork folder MAME reads.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.dom import minidom

from PIL import Image
from retrobox.paths import MAME_ARTWORK_DIR, SHARE_DIR, RUNTIME_DIR

from ...exceptions import RetroboxException
from ...utils import bezels as bezels_util
from ...utils.bezel_policy import BezelSettings, resolve_bezel_settings

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ...typedefs import Resolution
    from ...Emulator import Emulator

_logger = logging.getLogger(__name__)

_MAME_BIN = "/usr/bin/mame/mame"
_TATTOOED_BEZEL_PNG = RUNTIME_DIR / "bezel_tattooed.png"
# below this screen ratio (4:3 and the like) a bezel leaves no room for the game
_MIN_BEZEL_SCREEN_RATIO = 1.6
# 240 = half of the difference between 4:3 and 16:9 on 1920px (0.5 * 1920 / 16 * 4)
_TATTOO_WIDTH_RATIO = 240 / 1920
_TATTOO_MARGIN = 20  # pixels, vertical margin on a 1080p bezel
_ROTATED_ANGLES = (90, 270)
_DEFAULT_TATTOO = "generic.png"


@dataclass(frozen=True)
class MameBezelRequest:
    """Everything needed to configure the artwork of one game."""

    system: Emulator
    rom: Path
    resolution: Resolution
    bezel: str | None
    # the artwork folder is named after this machine, or after the rom if empty
    machine_name: str = ""


@dataclass(frozen=True)
class _Geometry:
    """Where the game screen sits inside the bezel image."""

    img_width: int
    img_height: int
    x_pos: int
    y_pos: int
    width: int
    height: int
    alpha: float = 1.0


def get_machine_size(machine: str, tmpdir: Path) -> tuple[int, int, int]:
    """Ask MAME for the size and rotation of the display of a machine.

    Args:
        machine: The machine (rom) name.
        tmpdir: A folder where the XML listing can be written.

    Returns:
        The width, height and rotation angle of the first display.

    Raises:
        RetroboxException: If MAME fails or the machine has no display.
    """
    with subprocess.Popen([_MAME_BIN, "-listxml", machine], stdout=subprocess.PIPE) as proc:
        out, _ = proc.communicate()
        exitcode = proc.returncode

    if exitcode != 0:
        raise RetroboxException(f"mame -listxml {machine} failed")

    infofile = tmpdir / "infos.xml"
    infofile.write_text(out.decode(), encoding="utf-8")

    infos = minidom.parse(str(infofile))
    for element in infos.getElementsByTagName("display"):
        return (
            int(element.getAttribute("width")),
            int(element.getAttribute("height")),
            int(element.getAttribute("rotate")),
        )

    raise RetroboxException("Display element not found")


def _geometry_from_info(info_file: Path) -> _Geometry:
    """Read the screen position from a bezel info file."""
    data = json.loads(info_file.read_text(encoding="utf-8"))
    return _Geometry(
        img_width=data["width"],
        img_height=data["height"],
        x_pos=data["left"],
        y_pos=data["top"],
        width=data["width"] - data["left"] - data["right"],
        height=data["height"] - data["top"] - data["bottom"],
        alpha=data.get("opacity", 1.0),  # just in case it is not set in the info file
    )


def _geometry_from_machine(rom: Path, bezel_png: Path, tmp_dir: Path) -> _Geometry:
    """Guess the screen position of a bezel without an info file.

    Assumes that all bezels are set up for 4:3 horizontal or 3:4 vertical aspects.
    """
    img_width, img_height = bezels_util.fast_image_size(bezel_png)
    _, _, rotate = get_machine_size(rom.stem, tmp_dir)

    if rotate in _ROTATED_ANGLES:
        width = int(img_height * (3 / 4))
    else:
        width = int(img_height * (4 / 3))
    return _Geometry(img_width, img_height, int((img_width - width) / 2), 0, width, img_height)


def _write_default_layout(layout_file: Path, geometry: _Geometry) -> None:
    """Write the MAME layout that puts the game screen inside the bezel."""
    layout_file.write_text(
        '<mamelayout version="2">\n'
        '<element name="bezel"><image file="default.png" /></element>\n'
        '<view name="bezel">\n'
        f'<screen index="0"><bounds x="{geometry.x_pos}" y="{geometry.y_pos}" '
        f'width="{geometry.width}" height="{geometry.height}" /></screen>\n'
        '<element ref="bezel"><bounds x="0" y="0" '
        f'width="{geometry.img_width}" height="{geometry.img_height}" '
        f'alpha="{geometry.alpha}" /></element>\n'
        "</view>\n"
        "</mamelayout>\n",
        encoding="utf-8",
    )


def _relink(link: Path, target: Path) -> None:
    """Point a symlink to a new target, replacing it if it exists."""
    link.unlink(missing_ok=True)
    link.symlink_to(target)


def _tattoo_file(system: Emulator, mode: str) -> Path:
    """Choose the tattoo image for a tattoo mode ("system", "custom", ...)."""
    overlays = SHARE_DIR / "controller-overlays"
    if mode == "system":
        path = overlays / f"{system.name}.png"
        return path if path.exists() else overlays / _DEFAULT_TATTOO

    if mode == "custom" and (custom := system.config.get_str("bezel.tattoo_file")):
        if Path(custom).exists():
            return Path(custom)
    return overlays / _DEFAULT_TATTOO


def _tattoo_position(
    corner: str, size: tuple[int, int], tattoo_size: tuple[int, int]
) -> tuple[int, int]:
    """Return where the tattoo is pasted for a corner name ("NW" by default)."""
    width, height = size
    tattoo_width, tattoo_height = tattoo_size
    positions = {
        "NE": (width - tattoo_width, _TATTOO_MARGIN),
        "SE": (width - tattoo_width, height - tattoo_height - _TATTOO_MARGIN),
        "SW": (0, height - tattoo_height - _TATTOO_MARGIN),
    }
    return positions.get(corner.upper(), (0, _TATTOO_MARGIN))


def _apply_tattoo(
    system: Emulator, bezel_link: Path, geometry: _Geometry, settings: BezelSettings
) -> None:
    """Draw the tattoo (controller image) on the bezel image behind ``bezel_link``."""
    tattoo_path = _tattoo_file(system, settings.tattoo)
    try:
        with Image.open(tattoo_path) as tattoo_file:
            tattoo = tattoo_file.convert("RGBA")
    except (OSError, ValueError):
        _logger.error("Error opening tattoo image: %s", tattoo_path)
        return

    size = (geometry.img_width, geometry.img_height)
    with Image.open(bezel_link) as bezel_file:
        back = bezel_file.convert("RGBA")

    tattoo_width = int(_TATTOO_WIDTH_RATIO * geometry.img_width)
    tattoo_height = int(float(tattoo.size[1]) * (tattoo_width / tattoo.size[0]))
    tattoo = tattoo.resize((tattoo_width, tattoo_height), Image.Resampling.LANCZOS)

    corner = system.config.get_str("bezel.tattoo_corner", "NW")
    back.paste(
        tattoo,
        _tattoo_position(corner, size, (tattoo_width, tattoo_height)),
        tattoo.split()[-1],
    )
    output = Image.new("RGBA", size, (0, 0, 0, 255))
    output.paste(back, (0, 0, *size))
    output.save(_TATTOOED_BEZEL_PNG, mode="RGBA", format="PNG")
    _relink(bezel_link, _TATTOOED_BEZEL_PNG)


def _find_bezel_files(request: MameBezelRequest) -> Mapping[str, Any] | None:
    """Find the bezel files of the game, or None when there is none."""
    if request.bezel is None:
        return None

    return bezels_util.get_bezel_infos(request.rom, request.bezel, request.system.name, "mame")


def _link_layout_bezel(files: Mapping[str, Any], art_dir: Path) -> tuple[Path, _Geometry]:
    """Link a bezel that ships its own MAME layout."""
    bezel_link = art_dir / files["png"].name
    (art_dir / "default.lay").symlink_to(files["layout"])
    bezel_link.symlink_to(files["png"])
    width, height = bezels_util.fast_image_size(files["png"])
    return bezel_link, _Geometry(width, height, 0, 0, width, height)


def _link_plain_bezel(
    request: MameBezelRequest, files: Mapping[str, Any], art_dir: Path
) -> tuple[Path, _Geometry]:
    """Link a plain bezel image and write the layout that frames the game with it."""
    bezel_link = art_dir / "default.png"
    bezel_link.symlink_to(files["png"])

    info_file = files.get("info")
    if info_file is not None and info_file.exists():
        geometry = _geometry_from_info(info_file)
    else:
        geometry = _geometry_from_machine(request.rom, files["png"], art_dir)

    _write_default_layout(art_dir / "default.lay", geometry)
    return bezel_link, geometry


def write_bezel_config(request: MameBezelRequest) -> None:
    """Create the artwork folder (or link) MAME reads for the game.

    Nothing is drawn when the bezel is switched off.

    Args:
        request: What to configure the artwork for.
    """
    name = request.machine_name or request.rom.stem
    art_dir = MAME_ARTWORK_DIR / name  # no need to zip, MAME takes a folder too
    # clean, in case no bezel is set, and in case we want to recreate it
    if art_dir.exists():
        shutil.rmtree(art_dir)

    if request.bezel is None:
        return

    screen_ratio = request.resolution["width"] / request.resolution["height"]
    if screen_ratio < _MIN_BEZEL_SCREEN_RATIO:
        return

    # let's generate the artwork folder
    art_dir.mkdir(parents=True)

    files = _find_bezel_files(request)
    if files is None:
        return

    mame_zip = files.get("mamezip")
    if mame_zip is not None and mame_zip.exists():
        art_file = MAME_ARTWORK_DIR / f"{name}.zip"
        art_file.unlink(missing_ok=True)
        art_file.symlink_to(mame_zip)
        return

    layout = files.get("layout")
    if layout is not None and layout.exists():
        bezel_link, geometry = _link_layout_bezel(files, art_dir)
    else:
        bezel_link, geometry = _link_plain_bezel(request, files, art_dir)

    settings = resolve_bezel_settings(request.system.config)
    if settings.has_tattoo:
        _apply_tattoo(request.system, bezel_link, geometry, settings)

