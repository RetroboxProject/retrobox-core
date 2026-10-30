"""Identification of the Model 2 set a ROM archive holds, from sm2-emu's games.xml.

sm2-emu identifies a set by the CRC32 of the chips in the archive, whatever
the archive is called. Retrobox does the same for the family of the game
(what the per-game button layout and the volume are keyed by): first from the
name of the archive, and else from the CRCs of a zip archive.
"""

from __future__ import annotations

import logging
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING, Final

from .sm2emu_paths import SM2EMU_GAMES_DB

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# games.xml is read by pugixml, which is not strict XML ("--" in comments), so
# the tags are scanned instead of parsing the file
_GAME: Final = re.compile(r"<game\s([^>]*)>(.*?)</game>", re.DOTALL)
_FILE_CRC: Final = re.compile(r"<file\s[^>]*\bcrc=\"(?:0x)?([0-9a-fA-F]+)\"")
_ATTRIBUTE: Final = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
# chips found in an archive before its family is taken for granted
_MIN_MATCHING_CHIPS: Final = 2


@dataclass(frozen=True)
class GamesDatabase:
    """What Retrobox needs from games.xml.

    Attributes:
        families: The family (the parent set, or the set itself) of every set.
        chips: The families each chip CRC belongs to.
    """

    families: dict[str, str] = field(default_factory=dict)
    chips: dict[int, frozenset[str]] = field(default_factory=dict)


@cache
def games_database() -> GamesDatabase:
    """Read games.xml once; an empty database when it cannot be read."""
    try:
        text = SM2EMU_GAMES_DB.read_text(encoding="utf-8")
    except OSError as error:
        _logger.debug("cannot read %s: %s", SM2EMU_GAMES_DB, error)
        return GamesDatabase()

    families: dict[str, str] = {}
    chips: dict[int, set[str]] = {}
    for game in _GAME.finditer(text):
        attributes = dict(_ATTRIBUTE.findall(game.group(1)))
        if not (name := attributes.get("name")):
            continue  # the schema in the leading comment
        family = attributes.get("parent") or name
        families[name] = family
        for crc in _FILE_CRC.findall(game.group(2)):
            chips.setdefault(int(crc, 16), set()).add(family)
    return GamesDatabase(families, {crc: frozenset(names) for crc, names in chips.items()})


def _family_from_chips(rom: Path) -> str | None:
    """Return the family most of the chips of a zip archive belong to."""
    if rom.suffix.lower() != ".zip":
        return None
    try:
        with zipfile.ZipFile(rom) as archive:
            crcs = [info.CRC for info in archive.infolist() if not info.is_dir()]
    except (OSError, zipfile.BadZipFile) as error:
        _logger.debug("cannot read the chips of %s: %s", rom, error)
        return None

    chips = games_database().chips
    votes = Counter(family for crc in crcs for family in chips.get(crc, ()))
    if not votes:
        return None
    family, matches = votes.most_common(1)[0]
    return family if matches >= _MIN_MATCHING_CHIPS else None


def game_set(rom: Path) -> str | None:
    """Return the set of a ROM, when the archive is named after a set of games.xml."""
    name = rom.stem.lower()
    return name if name in games_database().families else None


@cache
def game_family(rom: Path) -> str | None:
    """Return the family of the game of a ROM (its parent set, or the set), or None."""
    if (name := game_set(rom)) is not None:
        return games_database().families[name]
    if (family := _family_from_chips(rom)) is not None:
        _logger.debug("%s identified as the %s family from its chips", rom.name, family)
        return family
    _logger.info("%s is not a set sm2-emu knows: no per-game settings", rom.name)
    return None
