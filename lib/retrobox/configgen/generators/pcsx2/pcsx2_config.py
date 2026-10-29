"""PCSX2 configuration: PCSX2.ini.

Only the options that must work with this setup (folders, BIOS, input) or that
map to settings of the menu (graphics API, resolution, aspect ratio, audio
gain, fast boot, Discord) are written. The rest is left untouched, so the
choices made from PCSX2's own UI persist.

An option the menu manages is written on every launch, with its default when
the game does not set it, so a value picked for one game never leaks into the
next.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import CACHE, CHEATS, LOGS, ROMS, SAVES, SCREENSHOTS, mkdir_if_not_exists

from ...exceptions import RetroboxException
from ...utils import vulkan
from ...utils.audio_gain import gain_to_percent
from ...utils.discrete_gpu import discrete_gpu_property
from ...utils.configparser import CaseSensitiveConfigParser
from .pcsx2_controllers import _pcsx2_gen_controllers_config
from .pcsx2_paths import _PCSX2_BIOS, _PCSX2_CFGDIR, PCSX2_CFG

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ...typedefs import DeviceInfoMapping, Resolution
    from ...config import SystemConfig
    from ...controller import Controllers
    from ...Emulator import Emulator
    from ...gun import Guns

_logger = logging.getLogger(__name__)

# values of the Renderer option
RENDERER_AUTOMATIC = "-1"
RENDERER_OPENGL = "12"
RENDERER_SOFTWARE = "13"
RENDERER_VULKAN = "14"
_AUTO_VALUES = ("", "auto")

# values of the AspectRatio option
_RATIO_AUTO = "Auto 4:3/3:2"
_RATIO_STRETCH = "Stretch"
_RATIO_WIDE = "16:9"
_RATIO_STANDARD = "4:3"
_FMV_RATIO_OFF = "Off"
# what the menu stored for "Off" before its value was written as PCSX2 spells it
_FMV_RATIO_OFF_ALIASES = ("false", "off", "0")

_DEFAULT_BIOS = "ps2-0230e-20080220.bin"
_MAX_VOLUME = 200  # PCSX2 can amplify up to twice the volume (+6 dB)

_HOTKEYS = (
    ("ToggleFullscreen", "Keyboard/Alt & Keyboard/Return"),
    ("CycleAspectRatio", "Keyboard/F6"),
    ("CycleInterlaceMode", "Keyboard/F5"),
    ("CycleMipmapMode", "Keyboard/Insert"),
    ("GSDumpMultiFrame", "Keyboard/Control & Keyboard/Shift & Keyboard/F8"),
    ("Screenshot", "Keyboard/F8"),
    ("GSDumpSingleFrame", "Keyboard/Shift & Keyboard/F8"),
    ("ToggleSoftwareRendering", "Keyboard/F9"),
    ("ZoomIn", "Keyboard/Control & Keyboard/Plus"),
    ("ZoomOut", "Keyboard/Control & Keyboard/Minus"),
    ("InputRecToggleMode", "Keyboard/Shift & Keyboard/R"),
    ("LoadStateFromSlot", "Keyboard/F3"),
    ("SaveStateToSlot", "Keyboard/F1"),
    ("NextSaveStateSlot", "Keyboard/F2"),
    ("PreviousSaveStateSlot", "Keyboard/Shift & Keyboard/F2"),
    ("OpenPauseMenu", "Keyboard/Escape"),
    ("ToggleFrameLimit", "Keyboard/F4"),
    ("TogglePause", "Keyboard/Space"),
    ("ToggleSlowMotion", "Keyboard/Shift & Keyboard/Backtab"),
    ("ToggleTurbo", "Keyboard/Tab"),
    ("HoldTurbo", "Keyboard/Period"),
)


def _ensure_sections(settings: CaseSensitiveConfigParser, *sections: str) -> None:
    """Create the sections that are missing."""
    for section in sections:
        if not settings.has_section(section):
            settings.add_section(section)


def resolve_renderer(config: SystemConfig) -> str:
    """Return the Renderer value PCSX2 will use.

    Vulkan is the default. If it is not available on the system, PCSX2 picks the
    renderer itself (Automatic), which gives OpenGL there. OpenGL and Software
    are used as they are when the game asks for them.
    """
    requested = str(config.get("pcsx2_gfxbackend", RENDERER_VULKAN))
    if requested in _AUTO_VALUES:
        requested = RENDERER_VULKAN
    if requested == RENDERER_VULKAN and not vulkan.is_available():
        _logger.debug("Vulkan driver is not available on the system. Falling back to Automatic")
        return RENDERER_AUTOMATIC
    return requested


def uses_opengl(config: SystemConfig) -> bool:
    """Tell whether PCSX2 will render with OpenGL, which MangoHud has to be preloaded for."""
    return resolve_renderer(config) in (RENDERER_OPENGL, RENDERER_AUTOMATIC)


def _configure_folders(settings: CaseSensitiveConfigParser) -> None:
    """Point PCSX2 to the folders of this setup."""
    # remove inconsistent SaveStates casing if it exists
    settings.remove_option("Folders", "SaveStates")

    folders = {
        "Bios": _PCSX2_BIOS,
        "Snapshots": SCREENSHOTS,
        "Savestates": SAVES / "ps2" / "sstates",
        "MemoryCards": SAVES / "ps2" / "memcards",
        "Logs": LOGS,
        "Cheats": CHEATS / "ps2",
        "Cache": CACHE / "ps2",
        "Textures": _PCSX2_CFGDIR / "textures",
        "InputProfiles": _PCSX2_CFGDIR / "inputprofiles",
        "Videos": SAVES / "ps2" / "videos",
    }
    for option, folder in folders.items():
        settings.set("Folders", option, str(folder))
    mkdir_if_not_exists(CACHE / "ps2")


def _configure_bios(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Select the BIOS.

    Raises:
        RetroboxException: If the BIOS file is not found.
    """
    bios_file = str(config.get("pcsx2_forcebios", _DEFAULT_BIOS))
    if not Path(f"{_PCSX2_BIOS}/{bios_file}").is_file():
        raise RetroboxException(f"PS2 BIOS not found: {bios_file}")
    settings.set("Filenames", "BIOS", bios_file)


def _configure_emu_core(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the Discord presence and the fast boot."""
    settings.set(
        "EmuCore",
        "EnableDiscordPresence",
        config.get_bool("discordrpc", False, return_values=("true", "false")),
    )
    # fast boot skips the BIOS logo; it is on by default, like in PCSX2
    settings.set(
        "EmuCore",
        "EnableFastBoot",
        config.get_bool("pcsx2_fastboot", True, return_values=("true", "false")),
    )


def _configure_renderer(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the renderer and, for Vulkan, the GPU it runs on."""
    renderer = resolve_renderer(config)
    settings.set("EmuCore/GS", "Renderer", renderer)
    if renderer != RENDERER_VULKAN:
        return

    _logger.debug("Vulkan driver is available on the system.")
    discrete_name = discrete_gpu_property("PCSX2", "Name", vulkan.get_discrete_gpu_name)
    settings.set("EmuCore/GS", "Adapter", discrete_name or "(Default)")


def _configure_display(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the aspect ratios, the resolution and the integer scaling."""
    settings.set("EmuCore/GS", "AspectRatio", str(config.get("pcsx2_ratio", _RATIO_AUTO)))
    fmv_ratio = str(config.get("pcsx2_fmv_ratio", _FMV_RATIO_OFF))
    if fmv_ratio.lower() in _FMV_RATIO_OFF_ALIASES:
        fmv_ratio = _FMV_RATIO_OFF
    settings.set("EmuCore/GS", "FMVAspectRatioSwitch", fmv_ratio)
    settings.set("EmuCore/GS", "upscale_multiplier", str(config.get("pcsx2_resolution", "1")))
    settings.set(
        "EmuCore/GS",
        "IntegerScaling",
        config.get_bool("pcsx2_scaling", False, return_values=("true", "false")),
    )


def _configure_audio(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the volume that corresponds to the audio gain of the game, if it has one.

    The menu does not offer the gain for PCSX2 at the moment: without it the
    volume the user set in PCSX2's own UI stays.
    """
    gain = config.get("pcsx2_audio_gain")
    if gain is config.MISSING:
        return
    settings.set("SPU2/Output", "StandardVolume", str(gain_to_percent(gain, _MAX_VOLUME)))


def _clear_usb_wheels(settings: CaseSensitiveConfigParser) -> None:
    """Remove what a previous game left in the USB ports: wheels."""
    for port in ("USB1", "USB2"):
        if not settings.has_section(port):
            continue
        port_type = settings.get(port, "Type", fallback=None)
        if port_type == "Pad" and settings.get(port, "Pad_subtype", fallback=None) == "1":
            settings.remove_option(port, "Type")


# the arguments are the ones the controllers code needs
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def configure_ini(
    system: Emulator,
    controllers: Controllers,
    metadata: Mapping[str, str],
    guns: Guns,
    wheels: DeviceInfoMapping,
    playing_with_wheel: bool,
) -> None:
    """Update PCSX2.ini for the game."""
    mkdir_if_not_exists(PCSX2_CFG.parent)
    if not PCSX2_CFG.is_file():
        PCSX2_CFG.write_text("[UI]\n", encoding="utf-8")

    settings = CaseSensitiveConfigParser(interpolation=None)
    settings.read(PCSX2_CFG)
    _ensure_sections(
        settings, "Folders", "Filenames", "EmuCore", "EmuCore/GS", "SPU2/Output", "InputSources",
        "Hotkeys",
    )  # fmt: skip

    config = system.config
    _configure_folders(settings)
    _configure_bios(settings, config)
    _configure_emu_core(settings, config)
    _configure_renderer(settings, config)
    _configure_display(settings, config)
    _configure_audio(settings, config)

    settings.set("InputSources", "Keyboard", "true")
    settings.set("InputSources", "Mouse", "true")
    settings.set("InputSources", "SDL", "true")

    for option, value in _HOTKEYS:
        settings.set("Hotkeys", option, value)

    _clear_usb_wheels(settings)

    settings = _pcsx2_gen_controllers_config(
        settings, system, controllers, metadata, guns, wheels, playing_with_wheel
    )

    _ensure_sections(settings, "GameList")
    settings.set("GameList", "RecursivePaths", str(ROMS / "ps2"))

    with PCSX2_CFG.open("w", encoding="utf-8") as config_file:
        settings.write(config_file)


def bezel_fits(config: SystemConfig) -> bool:
    """Tell whether the picture is 4:3, the only shape a bezel is made for."""
    return str(config.get("pcsx2_ratio", _RATIO_AUTO)) in (_RATIO_AUTO, _RATIO_STANDARD)


def get_in_game_ratio(config: SystemConfig, resolution: Resolution) -> float:
    """Return the aspect ratio of the picture PCSX2 shows."""
    ratio = str(config.get("pcsx2_ratio", _RATIO_AUTO))
    if ratio == _RATIO_WIDE:
        return 16 / 9
    if ratio == _RATIO_STRETCH:
        # fills the window, so it depends on the physical screen
        return resolution["width"] / resolution["height"]
    return 4 / 3
