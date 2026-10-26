"""Choice of the MAME button layout (control scheme) of a game."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from .mamePaths import MAME_DEFAULT_DATA

if TYPE_CHECKING:
    from pathlib import Path

    from ...Emulator import Emulator
    from .mameTypes import MameControlScheme

# layouts the user can pick that are used as they are
_FIXED_LAYOUTS = ("default", "neomini", "neocd", "twinstick", "qbert")

# Games with 5-6 buttons: (game list file, scheme of each user layout). The
# first list that contains the game decides; a layout missing from its table
# falls back to "default".
_FIGHTING_GAMES: tuple[tuple[str, dict[str, str]], ...] = (
    (
        "mameCapcom.txt",
        {"auto": "sfsnes", "snes": "sfsnes", "megadrive": "megadrive", "fightstick": "sfstick"},
    ),
    (
        "mameMKombat.txt",
        {"auto": "mksnes", "snes": "mksnes", "megadrive": "mkmegadrive", "fightstick": "mkstick"},
    ),
    (
        "mameKInstinct.txt",
        {"auto": "kisnes", "snes": "kisnes", "megadrive": "megadrive", "fightstick": "sfstick"},
    ),
)
# games with unusual controls, whatever layout the user picked
_SPECIAL_GAMES = (
    ("mameNeogeo.txt", "neomini"),
    ("mameTwinstick.txt", "twinstick"),
    ("mameRotatedstick.txt", "qbert"),
)
# the scheme of every other game, for the layouts that change it
_OTHER_GAMES = {"fightstick": "fightstick", "megadrive": "mddefault"}


def _game_list(file_name: str) -> set[str]:
    """Read a list of game names from the MAME default data."""
    list_file: Path = MAME_DEFAULT_DATA / file_name
    return set(list_file.read_text(encoding="utf-8").split())


def get_control_scheme(system: Emulator, rom_path: Path) -> MameControlScheme:
    """Return the control scheme (button layout) of a game.

    Args:
        system: The running system, for the user "altlayout" option.
        rom_path: The game rom.

    Returns:
        The name of the control scheme.
    """
    layout = system.config.get("altlayout", "auto")
    if layout in _FIXED_LAYOUTS:
        return cast("MameControlScheme", layout)

    rom_name = rom_path.stem
    for file_name, schemes in _FIGHTING_GAMES:
        if rom_name in _game_list(file_name):
            return cast("MameControlScheme", schemes.get(layout, "default"))

    for file_name, scheme in _SPECIAL_GAMES:
        if rom_name in _game_list(file_name):
            return cast("MameControlScheme", scheme)

    return cast("MameControlScheme", _OTHER_GAMES.get(layout, "default"))
