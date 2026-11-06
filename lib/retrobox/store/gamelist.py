r"""The ``.batoexec`` files of packages: adding games to EmulationStation.

A batocera package may carry ``userdata/system/pacman/batoexec/<name>``, a text
file whose first line is ``command = argument``. Two commands exist there:

* ``gamelist = <system>``: the rest of the file is the ``<game>`` entries (or a
  ``<gameList>``) to add to that system, with their metadata and pictures.
* ``exec = <shell>``: shell code to run. It is **never** run here: a store
  package would run arbitrary code as the user, and the packages that need it
  (settings of batocera's own services) have no use on a desktop.

The entries are sent to EmulationStation's web service, or, if it is not
running, edited in the ``gamelist.xml`` of the system.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Final, Literal

from retrobox.paths import ROMS

from .state import is_valid_name

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

ES_SERVICE: Final = "http://127.0.0.1:1234"
_SERVICE_TIMEOUT: Final = 5
_ROOT_TAGS: Final = ("gameList", "gamelist", "game")

Mode = Literal["install", "uninstall"]


def _parse(text: str) -> tuple[str, str, str]:
    """Split a batoexec file into (command, argument, rest)."""
    first, _, rest = text.partition("\n")
    command, _, argument = first.partition("=")
    return command.strip(), argument.strip(), rest


def _games(rest: str) -> list[ET.Element]:
    """The ``<game>`` elements of the XML of a batoexec file."""
    root = ET.fromstring(rest)
    if root.tag not in _ROOT_TAGS:
        raise ValueError(f"unexpected root element <{root.tag}>")
    return [root] if root.tag == "game" else list(root.iter("game"))


def _call_service(system: str, games: list[ET.Element], mode: Mode) -> bool:
    """Ask EmulationStation to add or remove the games; False if it is not there."""
    endpoint = "addgames" if mode == "install" else "removegames"
    container = ET.Element("gameList")
    container.extend(games)
    request = urllib.request.Request(  # noqa: S310
        f"{ES_SERVICE}/{endpoint}/{system}",
        data=ET.tostring(container),
        headers={"Content-type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_SERVICE_TIMEOUT):  # noqa: S310
            return True
    except urllib.error.HTTPError as error:
        # it answered, so it is running: do not edit the file under its feet
        _logger.warning("EmulationStation did not take the games of %s: %s", system, error)
        return True
    except OSError:
        return False


def _edit_file(path: Path, games: list[ET.Element], mode: Mode) -> None:
    """Add or remove the games in a ``gamelist.xml``, creating it if needed."""
    if path.is_file():
        tree = ET.parse(path)  # noqa: S314
        root = tree.getroot()
    elif mode == "install":
        root = ET.Element("gameList")
        tree = ET.ElementTree(root)
    else:
        return

    wanted = {game.findtext("path", ""): game for game in games}
    wanted.pop("", None)
    present = {game.findtext("path", ""): game for game in root.findall("game")}
    if mode == "install":
        for game_path, game in wanted.items():
            if game_path not in present:
                root.append(game)
    else:
        for game_path in wanted:
            if game_path in present:
                root.remove(present[game_path])

    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def apply(text: str, mode: Mode, roms_dir: Path = ROMS) -> bool:
    """Do what a batoexec file says, if it is something this store does.

    Args:
        text: The content of the batoexec file.
        mode: Whether the package is being installed or removed.
        roms_dir: The ROMs directory, for the fallback of editing the file.

    Returns:
        Whether the file was understood and applied.
    """
    command, argument, rest = _parse(text)
    if command == "exec":
        _logger.warning("ignoring a shell command of the package (not run on purpose)")
        return False
    if command != "gamelist":
        _logger.debug("ignoring the batoexec command %r", command)
        return False
    if not is_valid_name(argument):
        _logger.warning("ignoring the gamelist of the invalid system %r", argument)
        return False

    try:
        games = _games(rest)
    except (ET.ParseError, ValueError) as error:
        _logger.warning("ignoring a malformed gamelist for %s: %s", argument, error)
        return False

    if not _call_service(argument, games, mode):
        _edit_file(roms_dir / argument / "gamelist.xml", games, mode)
    return True
