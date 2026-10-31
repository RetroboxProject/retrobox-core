"""Render the menu icons (packaging/icons/hicolor) from share/icons/retrobox_logo.png.

The logo's glow is an SVG blur filter, which Qt (KDE's menus and panels)
does not draw, so the desktop entry ships PNGs at the usual hicolor sizes
instead of the SVG. They are scaled down from the 512 px export of the SVG
(made with Inkscape, which draws the filter): re-run this after changing it.
The 512 px icon is that export itself (a link to it is installed), so it is
not duplicated here.

    python3 dev/render_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "share" / "icons" / "retrobox_logo.png"
TARGET = ROOT / "packaging" / "icons" / "hicolor"
SIZES = (16, 22, 24, 32, 48, 64, 96, 128, 256)


def main() -> None:
    """Write retrobox.png for every size in SIZES."""
    with Image.open(SOURCE) as source:
        # premultiplied alpha, so the transparent edges don't bleed dark fringes
        logo = source.convert("RGBA").convert("RGBa")
    for size in SIZES:
        icon = logo.resize((size, size), Image.Resampling.LANCZOS, reducing_gap=3.0)
        path = TARGET / f"{size}x{size}" / "apps" / "retrobox.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        icon.convert("RGBA").save(path, optimize=True)
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
