"""Read (and set a value of) EmulationStation's es_settings.cfg, and the confirm
button it uses.

EmulationStation (Linux build) names the face buttons of es_input.cfg by
position: ``a`` is the east button and ``b`` the south one. Its "Switch
confirm & cancel buttons" option (``InvertButtons``) decides which one
confirms: off (the default) the south button confirms and the east one goes
back, as on Xbox controllers; on, the east button confirms, as on Nintendo
controllers. Everything else Retrobox shows (the RetroArch menus, the setup
screen) follows the same choice, so the buttons behave the same everywhere.
"""

from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_logger = logging.getLogger(__name__)

_NEW_FILE = '<?xml version="1.0"?>\n<config>\n</config>\n'


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


def write_es_setting(path: Path, kind: str, name: str, value: str) -> bool:
    """Set one value of es_settings.cfg (``<kind name="name" value="value" />``).

    The entry of that name is replaced, or added at the end; the rest of the
    file is kept as it is. EmulationStation must not be running: it rewrites
    the file when it exits.

    Args:
        path: The es_settings.cfg to update (created if missing).
        kind: Its type in the file: ``bool``, ``int`` or ``string``.
        name: The setting.
        value: Its value, as EmulationStation writes it (``true``/``false``...).

    Returns:
        True if the file changed.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = _NEW_FILE
    except OSError as err:
        _logger.warning("Cannot read %s: %s", path, err)
        return False

    line = f"<{kind} name={quoteattr(name)} value={quoteattr(value)} />"
    entry = re.compile(rf"<\w+\s+name=([\"']){re.escape(name)}\1[^>]*/>")
    if entry.search(text):
        content = entry.sub(lambda _match: line, text)
    elif "</config>" in text:
        head, _, tail = text.rpartition("</config>")
        content = f"{head.rstrip(chr(10))}\n\t{line}\n</config>{tail}"
    else:  # older EmulationStation: no single root element, just the settings
        body = text.rstrip("\n")
        content = f"{body}\n{line}\n" if body else f"{line}\n"
    if content == text:
        return False

    temporary = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as err:
        _logger.warning("Cannot write %s: %s", path, err)
        temporary.unlink(missing_ok=True)
        return False
    return True
