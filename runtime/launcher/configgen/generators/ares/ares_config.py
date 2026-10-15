"""Ares configuration: settings.bml.

Ares reads one settings file (BML, nested by name). This module changes only
the settings that the menu of Retrobox manages, plus the controller mapping
and the firmware locations, and leaves every other setting as it already is in
the file. That way what is not offered in the menu (rewind, run ahead, the
threaded renderer, the color options...) can be set from Ares itself and it
is kept from one game to the next. A game that sets nothing runs as it always
did, because every managed setting has the default it had before the menu was
wired.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...utils.audio_gain import gain_to_percent
from .ares_bml import BmlNode, parse, render
from .ares_controllers import _ares_create_pads_config
from .ares_firmware import firmware_settings
from .ares_paths import _ARES_CFG, _ARES_CFGDIR, _ARES_SAVES, _ARES_SCREENSHOTS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from ...config import SystemConfig
    from ...Emulator import Emulator

_logger = logging.getLogger(__name__)

DEFAULT_VIDEO_DRIVER = "OpenGL 3.2"
OUTPUT_STRETCH = "Stretch"
ASPECT_ANAMORPHIC = "Anamorphic"

_MAX_VOLUME = 200  # Ares can amplify up to twice the volume (+6 dB)
_AUTO_VALUES = ("", "auto")
_DEFAULT_PAK_SIZE = "32KiB (Default)"
_DEFAULT_QUALITY = "SD"  # 1x native; HD is 2x and UHD is 4x
_DEFAULT_REGION = "NTSC-U"
_DEFAULT_PSX_PAD = "DualShock"  # the Digital Gamepad that Ares plugs in has no rumble
_PAD_SECTION_PREFIX = "VirtualPad"

# the controllers of the SNES ports Ares can remember: menu option -> Ares setting
_SNES_PORTS = {"ares_snes_port1": "ControllerPort1", "ares_snes_port2": "ControllerPort2"}

Section = dict[str, object]


def resolve_shader(shader_id: str | None, shaders_dir: Path) -> str:
    """Return the shader to use, or "None" if it is not set or not installed.

    The shader choice is shared with RetroArch (``system.renderconfig``), so it
    is the same whatever emulator runs. The id comes without extension, and the
    ``.slangp`` file must exist in share/ares/Shaders: a missing one must not
    break the start of Ares.
    """
    if not shader_id:
        return "None"

    rel_path = f"{shader_id}.slangp"
    if not (shaders_dir / rel_path).is_file():
        _logger.warning(
            "Ares shader '%s' not found at %s, falling back to None", rel_path, shaders_dir
        )
        return "None"
    return shader_id


def _saves_path_for(system: Emulator) -> str:
    """Return the saves folder of the system.

    The trailing slash is required: without it Ares appends the pretty name of
    the system to the last folder (".../saves/n64" + "Nintendo 64" becomes
    ".../saves/n64Nintendo 64") instead of creating a real subfolder.
    """
    return f"{_ARES_SAVES / system.name}/"


def _value(config: SystemConfig, key: str, default: str) -> str:
    """Return an option as text, with the default when it is unset or on "auto"."""
    value = str(config.get(key, default))
    return default if value in _AUTO_VALUES else value


def video_driver(config: SystemConfig) -> str:
    """Return the video driver of Ares ("OpenGL 3.2" is the only one on Linux)."""
    return _value(config, "ares_video_driver", DEFAULT_VIDEO_DRIVER)


def output_mode(config: SystemConfig) -> str:
    """Return how the picture fills the window: Scale, Integer or Stretch."""
    return _value(config, "ares_output", "Scale")


def aspect_correction(config: SystemConfig) -> str:
    """Return the aspect correction: None, Standard or Anamorphic."""
    return _value(config, "ares_aspect_correction", "Standard")


def region(config: SystemConfig) -> str:
    """Return the region of the console: NTSC-U, NTSC-J or PAL."""
    return _value(config, "ares_region", _DEFAULT_REGION)


def _video_section(config: SystemConfig) -> Section:
    """Build the [Video] section."""
    return {
        "Driver": video_driver(config),
        "Monitor": "Primary",
        "Format": "ARGB24",
        "Exclusive": False,
        "Blocking": config.get_bool("use_vsync"),
        "Flush": False,
        "Multiplier": 2,
        "Output": output_mode(config),
        "AspectCorrection": True,
        "AdaptiveSizing": True,
        "AutoCentering": False,
        "Luminance": "1.0",
        "Saturation": "1.0",
        "Gamma": "1.0",
        "ColorBleed": False,
        "Overscan": False,
        "PixelAccuracy": False,
        "PresentSRGB": False,
        "NativeFullScreen": True,
        "WindowWidth": 800,
        "WindowHeight": 576,
        "FixedScale": 2,
        "AspectCorrectionMode": aspect_correction(config),
    }


def _volume(config: SystemConfig) -> str:
    """Return the Ares volume (1.0 is the normal one) for the audio gain of the game."""
    percent = gain_to_percent(config.get("ares_audio_gain", "0"), _MAX_VOLUME)
    return str(round(percent / 100, 3))


def _audio_section(config: SystemConfig) -> Section:
    """Build the [Audio] section."""
    return {
        "Driver": _value(config, "ares_audio_driver", "SDL"),
        "Device": "Default",
        "Frequency": 48000,
        "Latency": _value(config, "ares_audio_latency", "40"),
        "Exclusive": False,
        "Blocking": True,
        "Dynamic": False,
        "Mute": False,
        "Volume": _volume(config),
        "Balance": "0.0",
    }


def _nintendo64_section(config: SystemConfig) -> Section:
    """Build the [Nintendo64] section: memory, Controller Pak size and render quality."""
    quality = _value(config, "ares_n64_quality", _DEFAULT_QUALITY)
    # supersampling scales 2x and 4x back to native, and does not work with weave deinterlacing
    supersampling = config.get_bool("ares_n64_supersampling") and quality != _DEFAULT_QUALITY
    return {
        "ExpansionPak": config.get_bool("ares_n64_expansion_pak", True),
        "ControllerPakBankString": _value(config, "ares_n64_cpak_size", _DEFAULT_PAK_SIZE),
        "Quality": quality,
        "Supersampling": supersampling,
        "DisableVideoInterfaceProcessing": False,
        "WeaveDeinterlacing": not supersampling,
    }


def _peripherals(config: SystemConfig, ports: Mapping[str, str]) -> Section:
    """Return the controller the game picked for each port.

    A port left on "auto" is written empty, so Ares plugs its own choice and
    the one of a previous game is not kept.
    """
    return {
        setting: "" if str(config.get(key, "")) in _AUTO_VALUES else str(config.get(key))
        for key, setting in ports.items()
    }


def _super_famicom_section(config: SystemConfig) -> Section:
    """Build the [SuperFamicom] section: deep black boost and the controllers."""
    return {
        "DeepBlackBoost": config.get_bool("ares_sfc_deep_black_boost"),
        **_peripherals(config, _SNES_PORTS),
    }


def _playstation_section(config: SystemConfig) -> Section:
    """Build the [PlayStation] section: the controller of both ports.

    Ares plugs a Digital Gamepad, which has no analog sticks and no rumble.
    """
    pad = _value(config, "ares_psx_pad", _DEFAULT_PSX_PAD)
    return {"ControllerPort1": pad, "ControllerPort2": pad}


def build_settings(config: SystemConfig, saves_path: str) -> dict[str, Section]:
    """Build the sections of settings.bml that the menu of Retrobox manages."""
    return {
        "Video": _video_section(config),
        "Audio": _audio_section(config),
        "Input": {"Driver": "SDL", "Defocus": "Pause"},
        "Boot": {
            "Fast": config.get_bool("ares_fast_boot"),
            "Debugger": False,
            "Prefer": region(config),
            "AwaitGDBClient": False,
        },
        "General": {
            "ShowStatusBar": True,
            "AutoSaveMemory": True,
            "HomebrewMode": False,
            "NoFilePrompt": True,
        },
        "Nintendo64": _nintendo64_section(config),
        "SuperFamicom": _super_famicom_section(config),
        "MegaDrive": {"TMSS": config.get_bool("ares_md_tmss")},
        "PlayStation": _playstation_section(config),
        "Paths": {
            "Home": f"{_ARES_CFGDIR}/",
            "Saves": saves_path,
            "Screenshots": _ARES_SCREENSHOTS,
        },
    }


def _read_settings() -> BmlNode:
    """Return the settings file as a tree, or an empty tree when there is none."""
    try:
        return parse(_ARES_CFG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return BmlNode()


def write_ares_config(system: Emulator, players_controllers) -> None:
    """Update settings.bml with the settings of the game, the firmware and the controllers."""
    settings = _read_settings()

    for section, options in build_settings(system.config, _saves_path_for(system)).items():
        for key, value in options.items():
            settings.set(f"{section}/{key}", value)

    for path, location in firmware_settings().items():
        settings.set(path, location)

    # the pads are rebuilt from the controllers of this game, never merged
    settings.remove_children(lambda name: name.startswith(_PAD_SECTION_PREFIX))
    settings.replace_children(parse(_ares_create_pads_config(players_controllers)))

    _ARES_CFG.write_text(render(settings), encoding="utf-8")
