"""Automatic start commands (``-autoboot_command``) of the MESS computers."""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .mame_game import MameGame
from .mameCommon import is_atom_floppy
from .mamePaths import MAME_CONFIG, MAME_DEFAULT_DATA

if TYPE_CHECKING:
    from .mame_command import CommandLine

_HASH_DIR = Path("/usr/bin/mame/hash")
_COCO_LIKE = ("coco", "dragon64")
_BBC_FLOPPY_BOOT = "*cat\\n\\n\\n\\n*exec !boot\\n"  # "\n" are typed into the emulator
_BBC_TAPE_BOOT = '*tape\\nchain""\\n'
_FM7_TAPE_BOOT = "LOADM”“,,R\\n"
_DEFAULT_DELAY = 3


@dataclass
class _AutoRun:
    """A command typed into the emulator after a delay."""

    command: str = ""
    delay: int = 0


def _overrides(csv_file: Path, rom_name: str, *, strict: bool, first_only: bool) -> str | None:
    """Look for the game in a user override file.

    Args:
        csv_file: The file, with ``game;command`` lines.
        rom_name: The game to look for.
        strict: Skip empty lines and comments (lines starting with "#").
        first_only: Stop at the first match instead of keeping the last one.

    Returns:
        The command to type, or None if the file has none for the game.
    """
    if not csv_file.exists():
        return None

    found = None
    with csv_file.open(encoding="utf-8") as file:
        for row in csv.reader(file, delimiter=";", quotechar="'"):
            if strict and (not row or row[0].startswith("#")):
                continue
            if row[0].casefold() == rom_name.casefold():
                found = f"{row[1]}\\n"
                if first_only:
                    break
    return found


def _soft_list_usage(game: MameGame) -> str:
    """Return the "usage" a software list gives for the game, or an empty string."""
    soft_list_file = _HASH_DIR / f"{game.soft_list}.xml"
    usage = ""
    if game.soft_list != "" and soft_list_file.exists():
        for software in ET.parse(soft_list_file).findall("software"):
            if software.attrib and software.get("name") == game.rom_name:
                for info in software.iter("info"):
                    if info.get("name") == "usage":
                        usage = f"{info.get('value')}\\n"
    return usage


def _is_cassette(game: MameGame) -> bool:
    """Tell whether the game is loaded from a cassette."""
    return (
        game.alt_rom_type == "cass"
        or bool(game.soft_list and game.soft_list.endswith("cass"))
        or game.rom.suffix.casefold() == ".cas"
    )


def _is_basic(game: MameGame) -> bool:
    """Tell whether the game is a BASIC program."""
    return game.rom_name.casefold().endswith(".bas")


def _bbc_micro(game: MameGame) -> _AutoRun:
    """Autostart of the BBC Micro: floppies and cassettes boot differently."""
    alt_type = game.alt_rom_type
    if alt_type or game.soft_list:
        if alt_type == "cass" or game.soft_list.endswith("cass"):
            return _AutoRun(_BBC_TAPE_BOOT, 2)
        if (alt_type and alt_type.startswith("flop")) or game.soft_list.endswith("flop"):
            return _AutoRun(_BBC_FLOPPY_BOOT, 3)
        return _AutoRun()
    return _AutoRun(_BBC_FLOPPY_BOOT, 3)


def _fm7(game: MameGame) -> _AutoRun:
    """Autostart of the FM-7: it boots floppies, so only cassettes need loading."""
    if game.alt_rom_type == "cass" or (game.soft_list and game.soft_list[-4:] == "cass"):
        return _AutoRun(_FM7_TAPE_BOOT, 5)
    return _AutoRun()


def _coco_like(game: MameGame) -> _AutoRun:
    """Autostart of the CoCo and the Dragon."""
    rom_type = "cart"
    command = _soft_list_usage(game)

    # if still undefined, default command based on media type
    if command == "":
        if _is_cassette(game):
            rom_type = "cass"
            command = "CLOAD:RUN\\n" if _is_basic(game) else "CLOADM:EXEC\\n"
        if (
            game.alt_rom_type == "flop1"
            or bool(game.soft_list and game.soft_list.endswith("flop"))
            or game.rom.suffix.casefold() == ".dsk"
        ):
            rom_type = "flop"
            if _is_basic(game):
                command = f'RUN "{game.rom_name}"\\n'
            else:
                command = f'LOADM "{game.rom_name}":EXEC\\n'

    # check for a user override
    override_file = MAME_CONFIG / "autoload" / f"{game.system.name}_{rom_type}_autoload.csv"
    command = _overrides(override_file, game.rom_name, strict=True, first_only=False) or command
    return _AutoRun(command, 2)


def _mc10(game: MameGame) -> _AutoRun:
    """Autostart of the MC-10."""
    rom_type = "cart"
    command = _soft_list_usage(game)

    if command == "" and _is_cassette(game):
        rom_type = "cass"
        command = "CLOAD\\n"

    override_file = MAME_CONFIG / "autoload" / f"{game.system.name}_{rom_type}_autoload.csv"
    command = _overrides(override_file, game.rom_name, strict=True, first_only=False) or command
    return _AutoRun(command, 2)


def _atom(game: MameGame) -> _AutoRun:
    """Autostart of the Atom: floppies have their own override file."""
    command = game.mess.auto_run if game.mess else ""
    is_floppy = (
        game.alt_rom_type == "flop1"
        or bool(game.soft_list and game.soft_list.endswith("flop"))
        or is_atom_floppy(game.rom)
    )
    if is_floppy:
        override_file = MAME_DEFAULT_DATA / "atom_flop_autoload.csv"
        command = _overrides(override_file, game.rom_name, strict=True, first_only=True) or command
    return _AutoRun(command, 1)


def _generic(game: MameGame) -> _AutoRun:
    """Autostart of the other systems: the one in messSystems.csv, or an override."""
    run = _AutoRun(game.mess.auto_run if game.mess else "", 0)
    override_file = MAME_DEFAULT_DATA / f"{game.soft_list}_autoload.csv"
    override = _overrides(override_file, game.rom_name, strict=False, first_only=False)
    if override is not None:
        run = _AutoRun(override, _DEFAULT_DELAY)
    return run


def autorun_options(game: MameGame) -> CommandLine:
    """Return the options that type a command into the emulator once it started."""
    name = game.system.name
    if name == "bbcmicro":
        run = _bbc_micro(game)
    elif name == "fm7":
        run = _fm7(game)
    elif name in _COCO_LIKE:
        run = _coco_like(game)
    elif name == "mc10":
        run = _mc10(game)
    elif name == "atom":
        run = _atom(game)
    else:
        run = _generic(game)

    if run.command == "":
        return []
    return ["-autoboot_delay", str(run.delay), "-autoboot_command", run.command]
