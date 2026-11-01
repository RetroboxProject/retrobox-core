"""Read EmulationStation's es_settings.cfg, and the confirm button it uses.

EmulationStation (Linux build) names the face buttons of es_input.cfg by
position: ``a`` is the east button and ``b`` the south one. Its "Switch
confirm & cancel buttons" option (``InvertButtons``) decides which one
confirms: off (the default) the south button confirms and the east one goes
back, as on Xbox controllers; on, the east button confirms, as on Nintendo
controllers. Everything else Retrobox shows (the RetroArch menus, the setup
screen) follows the same choice, so the buttons behave the same everywhere.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def read_es_settings(path: Path) -> dict[str, str]:
    """Every ``<type name="..." value="..."/>`` of es_settings.cfg.

    The file may have no single root element (older EmulationStation), so its
    content is wrapped in one before parsing.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    text = re.sub(r"<\?xml[^>]*\?>", "", text, count=1)
    try:
        root = ET.fromstring(f"<settings>{text}</settings>")
    except ET.ParseError:
        return {}
    return {
        element.get("name", ""): element.get("value", "")
        for element in root.iter()
        if element.get("name") is not None and element.get("value") is not None
    }


def confirm_is_east(settings: Mapping[str, str]) -> bool:
    """True when the east button confirms (``InvertButtons`` on), as on Nintendo pads."""
    return settings.get("InvertButtons", "").strip().lower() == "true"
