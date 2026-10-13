"""Cemu configuration: settings.xml.

Only the options that must work with this setup (paths, language, audio device)
or that map to settings of the menu are written; the rest is left untouched, so
the choices made from Cemu's own UI persist.

An option the menu manages is written on every launch, with its default when the
game does not set it, so a value picked for one game never leaks into the next.
"""

from __future__ import annotations

import logging
import os
import subprocess
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, cast
from xml.dom import minidom

from ...utils import vulkan
from ...utils.audio_gain import gain_to_percent
from ...utils.discrete_gpu import discrete_gpu_property
from .cemuPaths import CEMU_ROMDIR, CEMU_SAVES

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ...config import SystemConfig
    from ...Emulator import Emulator

_logger = logging.getLogger(__name__)

API_OPENGL = "0"
API_VULKAN = "1"
_AUTO_VALUES = ("", "auto")

_MAX_VOLUME = 100  # Cemu cannot amplify: 100 % is the loudest
_TEXT_COLOR = "4294967295"
_DEFAULT_LANGUAGE = "en_US"
_CEMU_LANGUAGES = {
    "ja_JP": 0, "en_US": 1, "fr_FR": 2, "de_DE": 3, "it_IT": 4, "es_ES": 5,
    "zh_CN": 6, "ko_KR": 7, "nl_NL": 8, "pt_PT": 9, "ru_RU": 10, "zh_TW": 11,
}  # fmt: skip

# what the performance overlay and the notifications show
_OVERLAY_FLAGS = ("FPS", "DrawCalls", "CPUUsage", "CPUPerCoreUsage", "RAMUsage", "VRAMUsage")
_NOTIFICATION_FLAGS = (
    "ControllerProfiles",
    "ControllerBattery",
    "ShaderCompiling",
    "FriendService",
)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def _get_root(document: minidom.Document, name: str) -> minidom.Element:
    """Return the first element called ``name``, creating it under the document if missing."""
    found = document.getElementsByTagName(name)
    if found:
        return found[0]
    element = document.createElement(name)
    document.appendChild(element)
    return element


def _set_value(
    document: minidom.Document, section: minidom.Element, name: str, value: str
) -> None:
    """Set the text of the element ``name`` of a section, creating it if missing."""
    found = section.getElementsByTagName(name)
    if found:
        element = found[0]
    else:
        element = document.createElement(name)
        section.appendChild(element)

    if element.hasChildNodes():
        cast("minidom.Text", element.firstChild).data = value
    else:
        element.appendChild(document.createTextNode(value))


def _set_group(
    document: minidom.Document,
    section: minidom.Element,
    name: str,
    values: Mapping[str, str],
) -> minidom.Element:
    """Create an element with children, and return it."""
    _set_value(document, section, name, "")
    group = _get_root(document, name)
    for key, value in values.items():
        _set_value(document, group, key, value)
    return group


# ---------------------------------------------------------------------------
# What the options mean
# ---------------------------------------------------------------------------


def resolve_api(config: SystemConfig) -> str:
    """Return the graphics API Cemu will use: Vulkan (1) or OpenGL (0).

    Vulkan is the default. OpenGL is used when the game asks for it, or when
    Vulkan is not available on the system.
    """
    requested = str(config.get("cemu_gfxbackend", API_VULKAN))
    if requested in _AUTO_VALUES:
        requested = API_VULKAN
    if requested == API_VULKAN and not vulkan.is_available():
        _logger.debug("Vulkan driver is not available on the system. Falling back to OpenGL")
        return API_OPENGL
    return requested


def _language_code(config: SystemConfig) -> int:
    """Return the Cemu number of the language of the console."""
    language = str(config.get("cemu_console_language", "ui"))
    if language == "ui":
        language = environ["LANG"][:5] if "LANG" in environ else _DEFAULT_LANGUAGE
    return _CEMU_LANGUAGES.get(language, _CEMU_LANGUAGES[_DEFAULT_LANGUAGE])


def _default_audio_device() -> str:
    """Return the default PipeWire/PulseAudio output, or an empty string."""
    try:
        result = subprocess.run(
            ["pactl", "get-default-sink"], capture_output=True, check=False, text=True
        )
    except OSError:
        return ""
    return result.stdout.strip()


def _flag(enabled: bool) -> str:  # noqa: FBT001
    return "true" if enabled else "false"


# ---------------------------------------------------------------------------
# Sections of settings.xml
# ---------------------------------------------------------------------------


def _configure_content(
    document: minidom.Document, content: minidom.Element, config: SystemConfig
) -> None:
    """Write the options of the root: paths, updates, window, gamepad and game folders."""
    for name, value in (
        ("mlc_path", str(CEMU_SAVES)),
        ("check_update", "false"),  # remove auto updates
        ("gp_download", "true"),  # avoid the welcome window
        ("logflag", "0"),
        ("advanced_ppc_logging", "false"),
        ("use_discord_presence", config.get_bool("discordrpc", return_values=("true", "false"))),
        ("fullscreen_menubar", "false"),
        ("vk_warning", "false"),
        ("fullscreen", "true"),
        ("console_language", str(_language_code(config))),
    ):
        _set_value(document, content, name, value)

    _set_group(document, content, "window_position", {"x": "0", "y": "0"})
    _set_group(document, content, "window_size", {"x": "640", "y": "480"})

    open_pad = config.get_bool("cemu_gamepad", return_values=("true", "false"))
    _set_value(document, content, "open_pad", open_pad)
    _set_group(document, content, "pad_position", {"x": "0", "y": "0"})
    _set_group(document, content, "pad_size", {"x": "640", "y": "480"})

    _set_group(document, content, "GamePaths", {"Entry": str(CEMU_ROMDIR)})


def _configure_device(document: minidom.Document, graphic: minidom.Element) -> None:
    """Use the discrete GPU for the Vulkan API, if there is one."""
    _logger.debug("Vulkan driver is available on the system.")
    if discrete_uuid := discrete_gpu_property("Cemu", "UUID", vulkan.get_discrete_gpu_uuid):
        _set_value(document, graphic, "device", discrete_uuid.replace("-", ""))


def _configure_graphic(
    document: minidom.Document, content: minidom.Element, config: SystemConfig
) -> None:
    """Write [Graphic]: API, VSync, filters, aspect ratio, overlay and notifications."""
    _set_value(document, content, "Graphic", "")
    graphic = _get_root(document, "Graphic")

    api = resolve_api(config)
    _set_value(document, graphic, "api", api)
    if api == API_VULKAN:
        _configure_device(document, graphic)

    for name, value in (
        ("AsyncCompile", config.get_bool("cemu_async", True, return_values=("true", "false"))),
        ("VSync", str(config.get("use_vsync", "0"))),  # 0 = off
        ("UpscaleFilter", str(config.get("cemu_upscale", "2"))),  # 2 = Hermite
        ("DownscaleFilter", str(config.get("cemu_downscale", "0"))),  # 0 = Bilinear
        ("FullscreenScaling", str(config.get("cemu_aspect", "0"))),  # 0 = keep the aspect ratio
    ):
        _set_value(document, graphic, name, value)

    # Cemu's own performance overlay: an alternative to MangoHud
    overlay = config.get_bool("cemu_overlay")
    base: dict[str, str] = {"Position": "3", "TextColor": _TEXT_COLOR, "TextScale": "100"}
    _set_group(
        document, graphic, "Overlay", {**base, **dict.fromkeys(_OVERLAY_FLAGS, _flag(overlay))}
    )

    notifications = config.get_bool("cemu_notifications")
    base = {"Position": "1", "TextColor": _TEXT_COLOR, "TextScale": "100"}
    _set_group(
        document,
        graphic,
        "Notification",
        {**base, **dict.fromkeys(_NOTIFICATION_FLAGS, _flag(notifications))},
    )


def _configure_audio(
    document: minidom.Document, content: minidom.Element, config: SystemConfig
) -> None:
    """Write [Audio]: API, channels, TV volume and output device."""
    _set_value(document, content, "Audio", "")
    audio = _get_root(document, "Audio")

    _set_value(document, audio, "api", "3")  # cubeb, the only option on Linux
    # audio only on the TV
    _set_value(document, audio, "TVChannels", str(config.get("cemu_audio_channels", "1")))
    # Cemu cannot amplify, so 0 dB is the loudest: a positive gain is the same as 0 dB
    volume = gain_to_percent(config.get("cemu_audio_gain", "0"), _MAX_VOLUME)
    _set_value(document, audio, "TVVolume", str(volume))

    # the output device is the default one of PipeWire, unless the user keeps their own
    audio_device = _default_audio_device()
    _logger.debug("*** audio device = %s ***", audio_device)
    if config.get_bool("cemu_audio_config", True):
        _set_value(document, audio, "TVDevice", audio_device)
    else:
        _logger.debug("*** use config audio device ***")


def write_settings(config_file: Path, system: Emulator) -> None:
    """Update Cemu's settings.xml for the game."""
    document = minidom.Document()
    if config_file.exists():
        try:
            document = minidom.parse(str(config_file))
        except Exception:  # pylint: disable=broad-exception-caught
            # whatever is wrong with the file (XML, encoding...): start a new one
            document = minidom.Document()

    content = _get_root(document, "content")
    _configure_content(document, content, system.config)
    _configure_graphic(document, content, system.config)
    _configure_audio(document, content, system.config)

    # remove the blank lines minidom adds
    lines = [line for line in document.toprettyxml().splitlines() if line.strip()]
    config_file.write_text(os.linesep.join(lines), encoding="utf-8")
