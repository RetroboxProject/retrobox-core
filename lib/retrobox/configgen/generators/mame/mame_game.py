"""What is known about a game before its MAME command line is built."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import TYPE_CHECKING

from retrobox.paths import DEFAULTS_DIR, ROMS

if TYPE_CHECKING:
    from pathlib import Path

    from ...Emulator import Emulator

# software lists whose games live one folder below the rom folder
SUBDIR_SOFT_LISTS = ("mac_hdd", "bbc_hdd", "cdi", "archimedes_hdd", "fmtowns_cd")

_MESS_SYSTEMS_CSV = DEFAULTS_DIR / "data" / "mame" / "messSystems.csv"
_NO_SOFT_LIST = "none"


@dataclass(frozen=True)
class MessRow:
    """The line of messSystems.csv that describes a MESS system."""

    sys_name: str
    rom_type: str
    auto_run: str


@dataclass
class MameGame:
    """The game MAME is about to run.

    Attributes:
        system: The running system.
        rom: The rom (or media) to run.
        mess: The MESS description of the system, None for an arcade game.
        soft_list: The software list of the game, empty if it has none.
        model: The MESS machine to emulate, filled in while the command is built.
        special_controller: A special controller picked by a system option.
    """

    system: Emulator
    rom: Path
    mess: MessRow | None
    soft_list: str
    model: str = ""
    special_controller: str = "none"

    @property
    def rom_name(self) -> str:
        """The rom file name without its extension."""
        return self.rom.stem

    @property
    def has_machine(self) -> bool:
        """Tell whether the game runs on a named MESS machine."""
        return self.mess is not None and self.mess.sys_name != ""

    @property
    def alt_rom_type(self) -> str:
        """The media type the user forced ("flop1", "cass"...), or an empty string."""
        return self.system.config.get_str("altromtype")


def _load_mess_rows() -> dict[str, MessRow]:
    """Read messSystems.csv: the MESS description of each system name."""
    rows: dict[str, MessRow] = {}
    with _MESS_SYSTEMS_CSV.open(encoding="utf-8") as csv_file:
        for row in csv.reader(csv_file, delimiter=";", quotechar="'"):
            # the first line of a system wins
            rows.setdefault(row[0], MessRow(row[1], row[2], row[3]))
    return rows


def _resolve_soft_list(system: Emulator, rom: Path) -> str:
    """Return the software list of the game, or an empty string."""
    soft_list = system.config.get_str("softList", _NO_SOFT_LIST)
    soft_list = soft_list if soft_list != _NO_SOFT_LIST else ""

    # Auto softlist for FM Towns if there is a zip that matches the folder name.
    # Used for games that require a CD and floppy to both be inserted
    if (
        system.name == "fmtowns"
        and soft_list == ""
        and (ROMS / "fmtowns" / f"{rom.parent.name}.zip").exists()
    ):
        soft_list = "fmtowns_cd"
    return soft_list


def create_game(system: Emulator, rom: Path) -> MameGame:
    """Collect what is known about the game before building its command line."""
    return MameGame(
        system=system,
        rom=rom,
        mess=_load_mess_rows().get(system.name),
        soft_list=_resolve_soft_list(system, rom),
    )
