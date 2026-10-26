"""Media options of a MESS machine: model, RAM, drives, software lists, blank disks."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from retrobox.paths import BIOS, MAME_SOFTWARE_DIR, mkdir_if_not_exists

from .mame_autorun import autorun_options
from .mame_game import SUBDIR_SOFT_LISTS
from .mamePaths import MAME_SAVES

if TYPE_CHECKING:
    from .mame_command import CommandLine
    from .mame_game import MameGame

_logger = logging.getLogger(__name__)

_MAC_FLOPPY_BOOTS = ("macos30", "macos608", "macos701", "macos75")
_APPLE2_DISK_EXTENSIONS = {".hdv", ".2mg", ".chd", ".iso", ".bin", ".cue"}
_MAC_RAM_MODELS = ("maciix", "maclc3")
_MAME_HASH_DIR = "/usr/bin/mame/hash"
_BLANK_DISK_DEFAULT = Path("/usr/share/mame/blank.default")
_BLANK_DISK_FMTOWNS = Path("/usr/share/mame/blank.fmtowns")
_MAX_MACLC3_RAM = 80


class _MediaRule(NamedTuple):
    """How the media option of a system depends on the rom extension."""

    fold_case: bool
    by_extension: dict[str, str]
    default: str


# systems whose media option is picked from the rom extension
_MEDIA_RULES = {
    "adam": _MediaRule(False, {".ddp": "-cass1", ".dsk": "-flop1"}, "-cart1"),
    "coco": _MediaRule(True, {".cas": "-cass", ".dsk": "-flop1"}, "-cart"),
    "dragon64": _MediaRule(True, {".cas": "-cass", ".dsk": "-flop1"}, "-cart"),
    "sc3000": _MediaRule(True, {".cas": "-cass", ".wav": "-cass", ".bit": "-cass"}, "-cart"),
    "segaai": _MediaRule(True, {".wav": "-cass", ".flac": "-cass", ".cas": "-cass"}, "-card"),
    "mc10": _MediaRule(True, {".cas": "-cass"}, "-cart"),
}


def _apple2_options(game: MameGame) -> CommandLine:
    """Options of the Apple II: SD/IDE control and the game port device."""
    config = game.system.config
    cmd: CommandLine = []
    # only add SD/IDE control if provided a hard drive image
    if game.rom.suffix.lower() in _APPLE2_DISK_EXTENSIONS:
        cmd += ["-sl7", "cffa202"]
    if (gameio := config.get("gameio", "none")) != "none":
        if gameio == "joyport" and game.model != "apple2p":
            _logger.debug("Joyport joystick is only compatible with Apple II Plus")
        else:
            cmd += ["-gameio", gameio]
            game.special_controller = gameio
    return cmd


def _system_extras(game: MameGame) -> CommandLine:
    """Options that only some systems need (expansions, joysticks...)."""
    name = game.system.name
    config = game.system.config
    cmd: CommandLine = []

    # TI-99 32k RAM expansion & speech modules - enabled by default
    if name == "ti99":
        cmd += ["-ioport", "peb"]
        if config.get_bool("ti99_32kram", True):
            cmd += ["-ioport:peb:slot2", "32kmem"]
        if config.get_bool("ti99_speech", True):
            cmd += ["-ioport", "speechsyn"]
    elif name == "laser310":  # memory expansion & joystick
        cmd += ["-io", "joystick", "-mem", config.get("memslot", "laser_64k")]
    elif name == "bbcmicro" and (sticktype := config.get("sticktype", "none")) != "none":
        cmd += ["-analogue", sticktype]
        game.special_controller = sticktype
    elif name == "enterprise":
        cmd += ["-exp", "exdos"]
    elif name == "apple2":
        cmd += _apple2_options(game)
    return cmd


def _mac_ram(model: str, ram_size: int) -> int:
    """Round the RAM size to one the Macintosh model accepts."""
    if model == "maclc3" and ram_size == 2:
        ram_size = 4
    if model == "maclc3" and ram_size > _MAX_MACLC3_RAM:
        ram_size = _MAX_MACLC3_RAM
    if model == "maciix" and ram_size == 16:
        ram_size = 32
    if model == "maciix" and ram_size == 48:
        ram_size = 64
    return ram_size


def _ram_options(game: MameGame) -> CommandLine:
    """RAM size, and the image reader of the Macintosh."""
    config = game.system.config
    ram_size = config.get_int("ramsize")
    if not ram_size:
        return []

    if game.system.name != "macintosh":
        return ["-ramsize", f"{ram_size}M"]

    cmd: CommandLine = []
    if game.model in _MAC_RAM_MODELS:
        cmd += ["-ramsize", f"{_mac_ram(game.model, ram_size)}M"]
    if game.model == "maciix":
        image_slot = config.get("imagereader", "nba")
        if image_slot != "disabled":
            cmd += [f"-{image_slot}", "image"]
    return cmd


def _generic_media(game: MameGame) -> CommandLine:
    """Media option of a system that is not a Macintosh."""
    assert game.mess is not None  # only called for MESS machines
    alt_type = game.alt_rom_type
    if alt_type:
        # only one drive on FMTMarty
        if game.model == "fmtmarty" and alt_type == "flop1":
            return ["-flop"]
        return [f"-{alt_type}"]

    rule = _MEDIA_RULES.get(game.system.name)
    if rule is None:
        return [f"-{game.mess.rom_type}"]
    extension = game.rom.suffix.casefold() if rule.fold_case else game.rom.suffix
    return [rule.by_extension.get(extension, rule.default)]


def _mac_media(game: MameGame, boot_disk: str | None) -> CommandLine:
    """Media option of the Macintosh: floppy 1 becomes 2 if a boot disk is enabled."""
    assert game.mess is not None  # only called for MESS machines
    alt_type = game.alt_rom_type
    if boot_disk and (alt_type == "flop1" or not alt_type) and boot_disk in _MAC_FLOPPY_BOOTS:
        return ["-flop2"]
    if alt_type:
        return [f"-{alt_type}"]
    return [f"-{game.mess.rom_type}"]


def _media_options(game: MameGame) -> CommandLine:
    """Drive options of a game that is not in a software list."""
    cmd: CommandLine = []
    boot_disk = game.system.config.get("bootdisk")
    is_mac = game.system.name == "macintosh"

    # Boot disk for Macintosh: uses floppy 1 or hard drive, depending on the disk
    if is_mac and boot_disk:
        if boot_disk in _MAC_FLOPPY_BOOTS:
            cmd += ["-flop1", f"{BIOS}/{boot_disk}.img"]
        else:
            cmd += ["-hard", f"{BIOS}/{boot_disk}.chd"]

    # Alternate ROM type for systems with multiple media (ie cassette & floppy)
    cmd += _mac_media(game, boot_disk) if is_mac else _generic_media(game)
    # use the full filename for MESS ROMs
    cmd.append(game.rom)
    return cmd


def _prepare_soft_list(game: MameGame) -> CommandLine:
    """Link the software list and the game folder, and name the game for MAME."""
    soft_dir = MAME_SOFTWARE_DIR
    soft_list = game.soft_list
    mkdir_if_not_exists(soft_dir)
    for check_file in soft_dir.iterdir():
        if check_file.is_symlink():
            check_file.unlink()
        if check_file.is_dir():
            shutil.rmtree(check_file)
    mkdir_if_not_exists(soft_dir / "hash")
    (soft_dir / "hash" / f"{soft_list}.xml").symlink_to(f"{_MAME_HASH_DIR}/{soft_list}.xml")

    rom_dir = game.rom.parent
    if soft_list in SUBDIR_SOFT_LISTS:
        (soft_dir / soft_list).symlink_to(rom_dir.parents[0], target_is_directory=True)
        return [rom_dir.name]
    (soft_dir / soft_list).symlink_to(rom_dir, target_is_directory=True)
    return [game.rom_name]


def _blank_disk_options(game: MameGame) -> CommandLine:
    """Create a blank disk and insert it into drive 2 (drive 1 in some cases)."""
    system = game.system
    if not system.config.get_bool("addblankdisk"):
        return []

    target_folder = MAME_SAVES / system.name
    if system.name == "fmtowns":
        blank_disk = _BLANK_DISK_FMTOWNS
        target_disk = target_folder / game.rom_name
    else:  # add elif statements here for other systems if enabled
        blank_disk = _BLANK_DISK_DEFAULT
        target_disk = target_folder / f"{game.rom_name}.default"
    mkdir_if_not_exists(target_folder)
    if not target_disk.exists():
        shutil.copy2(blank_disk, target_disk)

    # add other single floppy systems to this if statement
    if game.model == "fmtmarty":
        return ["-flop", target_disk]
    if system.config.get("altromtype") == "flop2":
        return ["-flop1", target_disk]
    return ["-flop2", target_disk]


def game_arguments(game: MameGame) -> CommandLine:
    """Return the model, media and autostart options that name the game.

    MESS uses the full filename and passes the system and rom type parameters
    when they are needed.
    """
    if not game.has_machine:
        return [game.rom.name]
    assert game.mess is not None  # has_machine implies a MESS row

    # alternate system for machines that have different configs (ie computers
    # with different hardware)
    game.model = game.system.config.get("altmodel") or game.mess.sys_name
    cmd: CommandLine = [game.model]
    cmd += _system_extras(game)
    cmd += _ram_options(game)
    cmd += _media_options(game) if game.soft_list == "" else _prepare_soft_list(game)
    cmd += _blank_disk_options(game)
    cmd += autorun_options(game)
    return cmd
