"""Sections of DuckStation's ``settings.ini`` that do not depend on the controllers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from runtime.paths import BIOS, CACHE, CHEATS, ROMS, SAVES, SCREENSHOTS, mkdir_if_not_exists

from ...exceptions import RetroboxException
from .duckstation_files import BIOS_LISTS, find_bios, get_language_from_environment

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ...config import SystemConfig
    from ...utils.configparser import CaseSensitiveConfigParser

_logger = logging.getLogger(__name__)

# the DuckStation settings version these options were written for
_SETTINGS_VERSION = "3"
# rewind: the option value -> (save slots, frequency)
_REWIND_SLOTS = {
    "120": ("120", "1"),
    "90": ("90", "1"),
    "60": ("60", "1"),
    "30": ("30", "1"),
    "15": ("15", "1"),
    "10": ("100", "0.100000"),
    "5": ("50", "0.050000"),
}
# RetroAchievements options: (user option, DuckStation option)
_CHEEVOS_FLAGS = (
    ("retroachievements.hardcore", "ChallengeMode"),
    ("retroachievements.richpresence", "RichPresence"),
    ("retroachievements.challenge_indicators", "PrimedIndicators"),
    ("retroachievements.leaderboards", "Leaderboards"),
    ("retroachievements.unofficial", "UnofficialTestMode"),
)
# the hotkeys are forced to be aligned with gamepadly
_HOTKEYS = {
    "FastForward": "Keyboard/Tab",
    "Reset": "Keyboard/F6",
    "LoadSelectedSaveState": "Keyboard/F1",
    "SaveSelectedSaveState": "Keyboard/F2",
    "SelectPreviousSaveStateSlot": "Keyboard/F3",
    "SelectNextSaveStateSlot": "Keyboard/F4",
    "Screenshot": "Keyboard/F10",
    "Rewind": "Keyboard/F5",
    "OpenPauseMenu": "Keyboard/F7",
    "ChangeDisc": "Keyboard/F8",
}
_INPUT_SOURCES = {
    "SDL": "true",
    "SDLControllerEnhancedMode": "false",
    "Evdev": "false",
    "XInput": "false",
    "RawInput": "false",
}
_DEFAULT_ASPECT_RATIO = "Auto (Game Native)"
_NATIVE_RATIO = "4:3"


def _section(settings: CaseSensitiveConfigParser, name: str, options: Mapping[str, str]) -> None:
    """Create a section if it is missing, and set its options in order."""
    if not settings.has_section(name):
        settings.add_section(name)
    for option, value in options.items():
        settings.set(name, option, value)


def _rewind_options(config: SystemConfig) -> dict[str, str]:
    """Return the rewind options. Rewind is only enabled for the known durations."""
    options = {"RewindEnable": "true", "RewindFrequency": "1"}
    slots_and_frequency = _REWIND_SLOTS.get(config.get("duckstation_rewind"))
    if slots_and_frequency is None:
        options["RewindEnable"] = "false"
    else:
        slots, options["RewindFrequency"] = slots_and_frequency
        options["RewindSaveSlots"] = slots  # total duration available in sec
    return options


def configure_main(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[Main]``: window behavior, overclock, rewind and language."""
    options = {
        "SettingsVersion": _SETTINGS_VERSION,  # probably to be updated in the future
        "InhibitScreensaver": "true",
        "StartPaused": "false",
        "StartFullscreen": "true",
        "PauseOnFocusLoss": "false",
        "PauseOnMenu": "true",
        "ConfirmPowerOff": "false",
        "ApplyGameSettings": "true",  # force applying game settings fixes
        "SetupWizardIncomplete": "false",  # remove wizard
        "EmulationSpeed": config.get("duckstation_clocking", "1"),  # overclock
        "SyncToHostRefreshRate": config.get("duckstation_hrr", "false"),
    }
    options.update(_rewind_options(config))
    options["EnableDiscordPresence"] = config.get_bool(
        "discordrpc", False, return_values=("true", "false")
    )
    options["Language"] = get_language_from_environment()
    _section(settings, "Main", options)


def configure_controller_ports(settings: CaseSensitiveConfigParser) -> None:
    """Write ``[ControllerPorts]``: the pointer scale, before the pads are added."""
    _section(
        settings,
        "ControllerPorts",
        {
            "ControllerSettingsMigrated": "true",
            "MultitapMode": "Disabled",
            "PointerXScale": "8",
            "PointerYScale": "8",
            "PointerXInvert": "false",
            "PointerYInvert": "false",
        },
    )


def configure_console(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[Console]``: region and cheats."""
    _section(
        settings,
        "Console",
        {
            "Region": config.get("duckstation_region", "Auto"),
            "EnableCheats": config.get("duckstation_cheats", "False"),
        },
    )


def configure_bios(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[BIOS]``: the search folder and the BIOS found for each region.

    Raises:
        RetroboxException: If no PSX BIOS is found.
    """
    _section(
        settings,
        "BIOS",
        {
            "SearchDirectory": f"{BIOS}",
            "PatchFastBoot": config.get("duckstation_PatchFastBoot", "false"),  # boot logo
        },
    )

    found_bios = find_bios(BIOS_LISTS)
    if not found_bios:
        raise RetroboxException("No PSX1 BIOS found")

    if forced_bios := _forced_bios(config):
        # the BIOS the user picked is used for every region
        for option in ("PathNTSCU", "PathPAL", "PathNTSCJ"):
            settings.set("BIOS", option, forced_bios)
    elif "Uni" in found_bios:
        # a universal BIOS covers every region
        uni_bios = found_bios["Uni"]
        for option in ("PathNTSCU", "PathPAL", "PathNTSCJ"):
            settings.set("BIOS", option, uni_bios)
    else:
        region_options = {"NTSCU": "PathNTSCU", "PAL": "PathPAL", "NTSCJ": "PathNTSCJ"}
        for region, bios in found_bios.items():
            settings.set("BIOS", region_options[region], bios)


def _forced_bios(config: SystemConfig) -> str | None:
    """Return the BIOS file the game asked for, or None if it did not or it is missing."""
    chosen = str(config.get("duckstation_bios", ""))
    if chosen in ("", "auto"):
        return None
    if not (BIOS / chosen).is_file():
        _logger.warning("The BIOS %s was asked for but is not in %s", chosen, BIOS)
        return None
    return chosen


def configure_cpu(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[CPU]``: the execution mode."""
    _section(
        settings,
        "CPU",
        {"ExecutionMode": config.get("duckstation_executionmode", "Recompiler")},
    )


def _antialiasing_options(antialiasing: str) -> dict[str, str]:
    """Return the multisampling options of an anti-aliasing mode like "4-ssaa" or "2"."""
    if "ssaa" in antialiasing:
        return {"PerSampleShading": "true", "Multisamples": antialiasing.split("-")[0]}
    return {"Multisamples": antialiasing, "PerSampleShading": "false"}


def configure_gpu(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[GPU]``: renderer, resolution, PGXP and anti-aliasing."""
    pgxp = config.get("duckstation_pgxp", "true")  # enabled by default
    _section(
        settings,
        "GPU",
        {
            "Renderer": config.get("duckstation_gfxbackend", "OpenGL"),
            # multisampling force (MSAA or SSAA): no GUI option anymore
            "PerSampleShading": "false",
            "Multisamples": "1",
            # threaded presentation (Vulkan improve)
            "ThreadedPresentation": config.get("duckstation_threadedpresentation", "false"),
            "ResolutionScale": config.get("duckstation_resolution_scale", "1"),
            "WidescreenHack": config.get("duckstation_widescreen_hack", "false"),
            "ForceNTSCTimings": config.get("duckstation_60hz", "false"),  # force 60hz
            "TextureFilter": config.get("duckstation_texture_filtering", "Nearest"),
            "PGXPEnable": pgxp,
            "PGXPCulling": pgxp,
            "PGXPTextureCorrection": pgxp,
            "PGXPPreserveProjFP": pgxp,
            "TrueColor": config.get("duckstation_truecolour", "false"),
            "ScaledDithering": config.get("duckstation_dithering", "true"),
            "DisableInterlacing": config.get("duckstation_interlacing", "false"),
        },
    )
    if antialiasing := config.get("duckstation_antialiasing"):
        for option, value in _antialiasing_options(antialiasing).items():
            settings.set("GPU", option, value)


def configure_display(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[Display]``: aspect ratio, scaling and filtering."""
    aspect_ratio = config.get("duckstation_ratio")
    _section(
        settings,
        "Display",
        {
            "AspectRatio": aspect_ratio or _DEFAULT_ASPECT_RATIO,
            "VSync": config.get("use_vsync", "false"),
            "CropMode": config.get("duckstation_CropMode", "Overscan"),
            "DisplayAllFrames": config.get("duckstation_ofp", "false"),  # optimal frame pacing
            "ShowOSDMessages": config.get("duckstation_osd", "false"),
            "IntegerScaling": config.get("duckstation_integer", "false"),
            "LinearFiltering": config.get("duckstation_linear", "false"),
            "Stretch": config.get("duckstation_stretch", "false"),
        },
    )


def bezel_fits_display(config: SystemConfig) -> bool:
    """Tell whether the display options leave room for a bezel.

    A ratio other than 4:3, or a stretched picture without integer scaling,
    leaves no room for it.
    """
    aspect_ratio = config.get("duckstation_ratio")
    if aspect_ratio is not config.MISSING and aspect_ratio != _NATIVE_RATIO:
        return False

    stretch = config.get("duckstation_stretch", "false")
    return not (stretch == "true" and config.get("duckstation_integer", "false") == "false")


def configure_audio(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[Audio]``: the stretch mode."""
    stretch_mode = config.get("duckstation_audio_mode", "TimeStretch")
    _section(settings, "Audio", {"StretchMode": stretch_mode})


def configure_game_list(settings: CaseSensitiveConfigParser) -> None:
    """Write ``[GameList]``: where the PSX games are."""
    _section(settings, "GameList", {"RecursivePaths": f"{ROMS}/psx"})


def configure_cheevos(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[Cheevos]``: the RetroAchievements account and options."""
    if not settings.has_section("Cheevos"):
        settings.add_section("Cheevos")

    if not config.get_bool("retroachievements"):
        settings.set("Cheevos", "Enabled", "false")
        return

    settings.set("Cheevos", "Enabled", "true")
    settings.set("Cheevos", "Username", config.get("retroachievements.username", ""))
    settings.set("Cheevos", "Token", config.get("retroachievements.token", ""))
    for user_option, option in _CHEEVOS_FLAGS:
        enabled = config.get(user_option, "") == "1"
        settings.set("Cheevos", option, "true" if enabled else "false")


def configure_texture_replacements(
    settings: CaseSensitiveConfigParser, config: SystemConfig
) -> None:
    """Write ``[TextureReplacements]``: normal mode by default."""
    # saves/textures/<psx game id>
    vram_write_replacements = "true"
    preload_textures = "false"
    match config.get("duckstation_custom_textures"):
        case "false" | "0":
            vram_write_replacements = "false"
        case "preload":
            preload_textures = "true"
    _section(
        settings,
        "TextureReplacements",
        {
            "EnableVRAMWriteReplacements": vram_write_replacements,
            "PreloadTextures": preload_textures,
        },
    )


def configure_input_sources(settings: CaseSensitiveConfigParser) -> None:
    """Write ``[InputSources]``: only SDL."""
    _section(settings, "InputSources", _INPUT_SOURCES)


def configure_folders(settings: CaseSensitiveConfigParser) -> None:
    """Write ``[MemoryCards]`` and ``[Folders]``, creating the folders they point to."""
    _section(settings, "MemoryCards", {"Directory": "../../../saves/duckstation/memcards"})

    if not settings.has_section("Folders"):
        settings.add_section("Folders")
    mkdir_if_not_exists(CACHE / "duckstation")
    settings.set("Folders", "Cache", "../../cache/duckstation")
    mkdir_if_not_exists(SCREENSHOTS)
    settings.set("Folders", "Screenshots", "../../../screenshots")
    mkdir_if_not_exists(SAVES / "duckstation")
    settings.set("Folders", "SaveStates", "../../../saves/duckstation")
    mkdir_if_not_exists(CHEATS / "duckstation")
    settings.set("Folders", "Cheats", "../../../cheats/duckstation")


def configure_hotkeys(settings: CaseSensitiveConfigParser) -> None:
    """Write ``[Hotkeys]``, forced to be aligned with gamepadly."""
    _section(settings, "Hotkeys", _HOTKEYS)
    if settings.has_option("Hotkeys", "OpenQuickMenu"):
        settings.remove_option("Hotkeys", "OpenQuickMenu")


def configure_cdrom_and_ui(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write ``[CDROM]`` and ``[UI]``."""
    _section(
        settings,
        "CDROM",
        {"AllowBootingWithoutSBIFile": config.get("duckstation_boot_without_sbi", "false")},
    )
    _section(settings, "UI", {"UnofficialBuildWarningConfirmed": "true"})
