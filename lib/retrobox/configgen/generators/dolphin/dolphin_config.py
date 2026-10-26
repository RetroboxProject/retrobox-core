"""Dolphin configuration: Dolphin.ini, GFX.ini, Hotkeys.ini and the Wii SYSCONF.

Only the options that must work with this setup (paths) or that map to
explicit settings of the menu (controller port type, graphics API, audio gain,
aspect ratio, internal resolution, Discord) are written.
The rest (cheats, dual core, VSync, anti-aliasing, hires textures...) is left
untouched, so the choices made from Dolphin's own UI persist.

An option the menu manages is written on every launch, with its default when the
game does not set it, so a value picked for one game never leaks into the next.
"""

from __future__ import annotations

import logging
import struct
from typing import TYPE_CHECKING, BinaryIO

from retrobox.paths import BIOS, ROMS, SAVES, mkdir_if_not_exists

from ...utils import vulkan
from ...utils.audio_gain import gain_to_percent
from ...utils.discrete_gpu import discrete_gpu_property
from ...utils.configparser import CaseSensitiveConfigParser
from .dolphin_paths import (
    _DOLPHIN_CFGDIR,
    _DOLPHIN_GC_CARD_A,
    _DOLPHIN_GC_CARD_B,
    _DOLPHIN_WII_NAND,
    _DOLPHIN_WII_RESPACKS,
    _DOLPHIN_WII_SDCARD_DIR,
    _DOLPHIN_WII_SDCARD_SYNC,
    _DOLPHIN_WII_WFSDIR,
    DOLPHIN_GFX_INI,
    DOLPHIN_INI,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from ...typedefs import DeviceInfoMapping, Resolution
    from ...config import SystemConfig
    from ...controller import Controllers
    from ...Emulator import Emulator

_logger = logging.getLogger(__name__)

BACKEND_VULKAN = "Vulkan"
BACKEND_OPENGL = "OGL"
_AUTO_VALUES = ("", "auto")

# values of the AspectRatio option of GFX.ini
_ASPECT_AUTO = "0"
_ASPECT_WIDE = "1"
_ASPECT_STANDARD = "2"
_ASPECT_STRETCH = "3"

_MAX_VOLUME = 100
_PORT_COUNT = 4
_STANDARD_CONTROLLER = "6"
_STEERING_WHEEL = "8"
_SYSCONF_BYTE = 3


# ---------------------------------------------------------------------------
# Dolphin.ini
# ---------------------------------------------------------------------------


def _ensure_sections(settings: CaseSensitiveConfigParser, sections: tuple[str, ...]) -> None:
    """Create the sections that are missing."""
    for section in sections:
        if not settings.has_section(section):
            settings.add_section(section)


def write_dolphin_ini(
    system: Emulator, controllers: Controllers, wheels: DeviceInfoMapping
) -> None:
    """Update Dolphin.ini: paths, Discord, graphics API, audio gain and port devices."""
    mkdir_if_not_exists(DOLPHIN_INI.parent)

    settings = CaseSensitiveConfigParser(interpolation=None)
    if DOLPHIN_INI.exists():
        settings.read(DOLPHIN_INI)
    _ensure_sections(settings, ("General", "Core", "GBA", "DSP"))

    _configure_paths(settings)
    _configure_discord_rpc(settings, system)
    configure_gfx_backend(settings, system)
    _configure_audio(settings, system.config)
    configure_controller_ports(settings, system, controllers, wheels)

    with DOLPHIN_INI.open("w", encoding="utf-8") as config_file:
        settings.write(config_file)


def _configure_paths(settings: CaseSensitiveConfigParser) -> None:
    """Point Dolphin to the folders of this setup."""
    # Default games path (only set once, so the user can still change it from Dolphin's UI)
    if "ISOPaths" not in settings["General"]:
        settings.set("General", "ISOPath0", f"{ROMS}/wii")
        settings.set("General", "ISOPath1", f"{ROMS}/gamecube")
        settings.set("General", "ISOPaths", "2")

    for folder in (
        _DOLPHIN_WII_NAND,
        _DOLPHIN_WII_RESPACKS,
        _DOLPHIN_WII_WFSDIR,
        _DOLPHIN_WII_SDCARD_DIR,
        _DOLPHIN_WII_SDCARD_SYNC,
        _DOLPHIN_GC_CARD_A,
        _DOLPHIN_GC_CARD_B,
        SAVES / "gba" / "dolphin_emu",
    ):
        mkdir_if_not_exists(folder)

    settings.set("General", "DumpPath", str(_DOLPHIN_CFGDIR / "Dump/"))
    settings.set("General", "LoadPath", str(_DOLPHIN_CFGDIR / "Load/"))
    settings.set("General", "NANDRootPath", str(_DOLPHIN_WII_NAND))
    settings.set("General", "ResourcePackPath", str(_DOLPHIN_WII_RESPACKS))
    settings.set("General", "WFSPath", str(_DOLPHIN_WII_WFSDIR))
    settings.set("General", "WiiSDCardPath", str(_DOLPHIN_WII_SDCARD_DIR / "WiiSD.raw"))
    settings.set("General", "WiiSDCardSyncFolder", str(_DOLPHIN_WII_SDCARD_SYNC))

    settings.set("Core", "GCIFolderAPath", str(_DOLPHIN_GC_CARD_A))
    settings.set("Core", "GCIFolderBPath", str(_DOLPHIN_GC_CARD_B))

    settings.set("GBA", "BIOS", str(BIOS / "gba_bios.bin"))
    settings.set("GBA", "SavesPath", str(SAVES / "gba" / "dolphin_emu"))


def _configure_discord_rpc(settings: CaseSensitiveConfigParser, system: Emulator) -> None:
    """Enable or disable the Discord presence."""
    settings.set("General", "UseDiscordPresence", str(system.config.get_bool("discordrpc", False)))


def resolve_gfx_backend(config: SystemConfig) -> str:
    """Return the graphics API Dolphin will use: "Vulkan" or "OGL".

    Vulkan is the default, and OpenGL is used when the game asks for it or when
    Vulkan is not available on the system.
    """
    requested = str(config.get("gfxbackend", BACKEND_VULKAN))
    if requested in (*_AUTO_VALUES, BACKEND_VULKAN):
        if vulkan.is_available():
            return BACKEND_VULKAN
        _logger.debug("Vulkan driver is not available on the system. Using OpenGL instead.")
    return BACKEND_OPENGL


def configure_gfx_backend(settings: CaseSensitiveConfigParser, system: Emulator) -> None:
    """Write the graphics API."""
    settings.set("Core", "GFXBackend", resolve_gfx_backend(system.config))


def _configure_audio(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the volume that corresponds to the audio gain of the game, if it has one.

    The menu does not offer the gain for Dolphin at the moment: without it the
    volume the user set in Dolphin's own UI stays.
    """
    gain = config.get("dolphin_audio_gain")
    if gain is config.MISSING:
        return
    # Dolphin cannot amplify, so 0 dB is the loudest: a positive gain is the same as 0 dB
    settings.set("DSP", "Volume", str(gain_to_percent(gain, _MAX_VOLUME)))


def _default_port_device(
    system: Emulator, controllers: Controllers, wheels: DeviceInfoMapping, port: int
) -> str:
    """Return the device of a GameCube port that the game did not set."""
    has_wheel = (
        system.name == "gamecube"
        and system.config.use_wheels
        and wheels
        and port < len(controllers)
        and controllers[port].device_path in wheels
    )
    return _STEERING_WHEEL if has_wheel else _STANDARD_CONTROLLER


def configure_controller_ports(
    settings: CaseSensitiveConfigParser,
    system: Emulator,
    controllers: Controllers,
    wheels: DeviceInfoMapping,
) -> None:
    """Write the device plugged into each GameCube port."""
    for port in range(_PORT_COUNT):
        if value := system.config.get(f"dolphin_port_{port + 1}_type"):
            # 6a/6b both map to "Standard Controller" (6); the a/b split only
            # differentiates button layout, handled in dolphin_controllers.
            device = _STANDARD_CONTROLLER if value in ("6a", "6b") else str(value)
        else:
            device = _default_port_device(system, controllers, wheels, port)
        settings.set("Core", f"SIDevice{port}", device)

    # Triforce wheel: both ports must be GC Steering (8) for baseboard detection.
    if system.name == "triforce" and system.config.use_wheels and wheels:
        for port in (0, 1):
            if not system.config.get(f"dolphin_port_{port + 1}_type"):
                settings.set("Core", f"SIDevice{port}", _STEERING_WHEEL)


# ---------------------------------------------------------------------------
# GFX.ini
# ---------------------------------------------------------------------------


def write_gfx_ini(system: Emulator) -> None:
    """Update GFX.ini: aspect ratio, widescreen hack and internal resolution."""
    settings = CaseSensitiveConfigParser(interpolation=None)
    settings.read(DOLPHIN_GFX_INI)
    _ensure_sections(settings, ("Settings", "Hardware"))

    _configure_gpu_adapter(settings)
    config = system.config

    # Aspect Ratio: 0 Auto / 1 Force 16:9 / 2 Force 4:3 / 3 Stretch
    settings.set("Settings", "AspectRatio", str(config.get("dolphin_aspect_ratio", _ASPECT_AUTO)))

    # Widescreen hack, needed to actually get 16:9 out of GameCube titles
    # that don't support it natively when aspect ratio is forced/auto'd to 16:9.
    settings.set("Settings", "wideScreenHack", str(config.get_bool("widescreen_hack")))

    # Internal resolution / scaling multiplier (1 = native, 2 = 2x, ...)
    settings.set("Settings", "InternalResolution", str(config.get("internal_resolution", "1")))

    with DOLPHIN_GFX_INI.open("w", encoding="utf-8") as config_file:
        settings.write(config_file)


def _configure_gpu_adapter(settings: CaseSensitiveConfigParser) -> None:
    """Use the discrete GPU for the Vulkan backend, if there is one."""
    if not vulkan.is_available():
        return
    _logger.debug("Vulkan driver is available on the system.")
    if discrete_index := discrete_gpu_property("Dolphin", "Index", vulkan.get_discrete_gpu_index):
        settings.set("Hardware", "Adapter", discrete_index)


# ---------------------------------------------------------------------------
# Hotkeys.ini - overwritten in full each launch
# ---------------------------------------------------------------------------

_HOTKEYS = (
    ("Device", "XInput2/0/Virtual core pointer"),
    ("General/Open", "@(Ctrl+O)"),
    ("General/Toggle Pause", "F10"),
    ("General/Stop", "Escape"),
    ("General/Toggle Fullscreen", "@(Alt+Return)"),
    ("General/Take Screenshot", "F9"),
    ("General/Exit", "@(Shift+F11)"),
    ("Emulation Speed/Disable Emulation Speed Limit", "Tab"),
    ("Stepping/Step Into", "F11"),
    ("Stepping/Step Over", "@(Shift+F10)"),
    ("Stepping/Step Out", "@(Shift+F11)"),
    ("Breakpoint/Toggle Breakpoint", "@(Shift+F9)"),
    ("Wii/Connect Wii Remote 1", "@(Alt+F5)"),
    ("Wii/Connect Wii Remote 2", "@(Alt+F6)"),
    ("Wii/Connect Wii Remote 3", "@(Alt+F7)"),
    ("Wii/Connect Wii Remote 4", "@(Alt+F8)"),
    ("Wii/Connect Balance Board", "@(Alt+F9)"),
    ("Other State Hotkeys/Increase Selected State Slot", "@(Shift+F1)"),
    ("Other State Hotkeys/Decrease Selected State Slot", "@(Shift+F2)"),
    ("Load State/Load from Selected Slot", "F8"),
    ("Save State/Save to Selected Slot", "F5"),
    ("Other State Hotkeys/Undo Load State", "@(Shift+F12)"),
    ("GBA Core/Load ROM", "@(`Ctrl`+`Shift`+`O`)"),
    ("GBA Core/Unload ROM", "@(`Ctrl`+`Shift`+`W`)"),
    ("GBA Core/Reset", "@(`Ctrl`+`Shift`+`R`)"),
    ("GBA Volume/Volume Down", "`KP_Subtract`"),
    ("GBA Volume/Volume Up", "`KP_Add`"),
    ("GBA Volume/Volume Toggle Mute", "`M`"),
    ("GBA Window Size/1x", "`KP_1`"),
    ("GBA Window Size/2x", "`KP_2`"),
    ("GBA Window Size/3x", "`KP_3`"),
    ("GBA Window Size/4x", "`KP_4`"),
    ("USB Emulation Devices/Show Skylanders Portal", "@(Ctrl+P)"),
    ("USB Emulation Devices/Show Infinity Base", "@(Ctrl+I)"),
)  # fmt: skip


def write_hotkeys_ini() -> None:
    """Write Hotkeys.ini."""
    settings = CaseSensitiveConfigParser(interpolation=None)
    settings.add_section("Hotkeys")
    for key, value in _HOTKEYS:
        settings.set("Hotkeys", key, value)

    with (_DOLPHIN_CFGDIR / "Hotkeys.ini").open("w", encoding="utf-8") as config_file:
        settings.write(config_file)


# ---------------------------------------------------------------------------
# SYSCONF - only the Wii's internal aspect-ratio flag (IPL.AR) is kept in sync
# with the menu. Language and sensor bar position are left as Wii-menu-level
# settings.
# ---------------------------------------------------------------------------


def _read_be_int16(file: BinaryIO) -> int:
    return struct.unpack(">H", file.read(2))[0]


def _read_be_int32(file: BinaryIO) -> int:
    return struct.unpack(">L", file.read(4))[0]


def _read_int8(file: BinaryIO) -> int:
    return struct.unpack("B", file.read(1))[0]


def _skip_value(file: BinaryIO, item_type: int) -> None:
    """Skip the value of a SYSCONF entry."""
    if item_type == 1:  # big array
        file.read(_read_be_int16(file) + 1)
    elif item_type == 2:  # small array
        file.read(_read_int8(file) + 1)
    elif item_type == _SYSCONF_BYTE:
        _read_int8(file)
    elif item_type == 4:  # short
        _read_be_int16(file)
    elif item_type == 5:  # long
        _read_be_int32(file)
    elif item_type == 6:  # long long
        file.read(8)
    elif item_type == 7:  # bool
        _read_int8(file)
    else:
        raise ValueError(f"unknown type {item_type}")


def _read_write_entry(file: BinaryIO, new_values: Mapping[str, int]) -> None:
    """Read a SYSCONF entry, overwriting its value if it is in ``new_values``."""
    item_header = _read_int8(file)
    item_type = (item_header & 0xE0) >> 5
    name_length = (item_header & 0x1F) + 1
    item_name = file.read(name_length).decode("utf-8")

    if item_name not in new_values:
        _skip_value(file, item_type)
    elif item_type == _SYSCONF_BYTE:
        file.write(struct.pack("B", new_values[item_name]))
    else:
        raise ValueError(f"not writable type {item_type}")


def get_ratio_from_config(config: SystemConfig) -> int:
    """Return the Wii's internal aspect ratio flag: 0 for 4:3, 1 for 16:9."""
    return 1 if config.get("tv_mode") == "1" else 0


def update_sysconf_aspect_ratio(config: SystemConfig, filepath: Path) -> None:
    """Keep the Wii's internal aspect ratio flag (IPL.AR) in sync with the menu."""
    if not filepath.exists():
        return

    new_values = {"IPL.AR": get_ratio_from_config(config)}
    try:
        with filepath.open("r+b") as file:
            file.read(4)  # "SCv0" header
            entries = _read_be_int16(file)
            file.read((entries + 1) * 2)  # offsets table
            for _ in range(entries):
                _read_write_entry(file, new_values)
    except (OSError, ValueError, struct.error):
        _logger.warning("Couldn't update the SYSCONF aspect ratio flag", exc_info=True)


# ---------------------------------------------------------------------------
# Output ratio. Dolphin does not need it: the bezels and the other launcher
# code do. It mirrors the AspectRatio option above and the Wii TV mode.
# ---------------------------------------------------------------------------


def _auto_ratio_is_wide(config: SystemConfig) -> bool:
    """Tell whether the "Auto" aspect ratio gives 16:9: a 16:9 Wii TV or the widescreen hack."""
    return get_ratio_from_config(config) == 1 or config.get_bool("widescreen_hack")


def bezel_fits(config: SystemConfig) -> bool:
    """Tell whether the picture is 4:3, the only shape a bezel is made for."""
    mode = str(config.get("dolphin_aspect_ratio", _ASPECT_AUTO))
    if mode == _ASPECT_STANDARD:
        return True
    if mode == _ASPECT_AUTO:
        return not _auto_ratio_is_wide(config)
    return False  # forced 16:9, stretched to the window, or a custom ratio


def get_in_game_ratio(config: SystemConfig, resolution: Resolution) -> float:
    """Return the aspect ratio of the picture Dolphin shows."""
    settings = CaseSensitiveConfigParser(interpolation=None)
    settings.read(DOLPHIN_GFX_INI)
    mode = settings.get("Settings", "AspectRatio", fallback=_ASPECT_AUTO)

    if mode == _ASPECT_AUTO:
        return 16 / 9 if _auto_ratio_is_wide(config) else 4 / 3
    if mode == _ASPECT_WIDE:
        return 16 / 9
    if mode == _ASPECT_STRETCH:
        # depends on the physical screen geometry
        return resolution["width"] / resolution["height"]
    return 4 / 3
