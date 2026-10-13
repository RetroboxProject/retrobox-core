"""PPSSPP configuration: ppsspp.ini.

Only the options that must work with this setup or that map to settings of the
menu are written; the rest is left untouched, so the choices made from PPSSPP's
own UI persist.

An option the menu manages is written on every launch, with its default when the
game does not set it, so a value picked for one game never leaks into the next.
"""

# the module name follows the <emulator>Config convention of the generators
# pylint: disable=invalid-name

from __future__ import annotations

import configparser
import getpass
import logging
from typing import TYPE_CHECKING, Final

from runtime.paths import ensure_parents_and_open

from ...utils import vulkan
from ...utils.audio_gain import gain_to_percent
from ...utils.discrete_gpu import discrete_gpu_property
from ...utils.configparser import CaseSensitiveConfigParser
from .ppssppPaths import _PPSSPP_SYSDIR

if TYPE_CHECKING:
    from ...config import SystemConfig
    from ...Emulator import Emulator

_logger = logging.getLogger(__name__)

_PPSSPP_INI: Final = _PPSSPP_SYSDIR / "ppsspp.ini"
_RETROACHIEVEMENTS_TOKEN: Final = _PPSSPP_SYSDIR / "ppsspp_retroachievements.dat"

# values of the GraphicsBackend option
BACKEND_OPENGL = "0 (OPENGL)"
BACKEND_VULKAN = "3 (VULKAN)"
_AUTO_VALUES = ("", "auto")

_MAX_VOLUME = 100  # PPSSPP cannot amplify: 100 % is the loudest
_FPS_COUNTER_BOTH = "3"  # 1 for Speed%, 2 for FPS, 3 for both
_REWIND_EVERY_5_SECONDS = "300"


def resolve_gfx_backend(config: SystemConfig) -> str:
    """Return the graphics API PPSSPP will use.

    Vulkan is the default. OpenGL is used when the game asks for it, or when
    Vulkan is not available on the system.
    """
    requested = str(config.get("gfxbackend", BACKEND_VULKAN))
    if requested in _AUTO_VALUES:
        requested = BACKEND_VULKAN
    if requested == BACKEND_VULKAN and not vulkan.is_available():
        _logger.debug("Vulkan driver is not available on the system. Falling back to OpenGL")
        return BACKEND_OPENGL
    return requested


def uses_opengl(config: SystemConfig) -> bool:
    """Tell whether PPSSPP will render with OpenGL, which MangoHud has to be preloaded for."""
    return resolve_gfx_backend(config) == BACKEND_OPENGL


def _bool(config: SystemConfig, key: str, default: bool = False) -> str:
    """Return a boolean option as the "True" or "False" text of PPSSPP's ini."""
    return str(config.get_bool(key, default))


def _ensure_sections(settings: CaseSensitiveConfigParser, *sections: str) -> None:
    """Create the sections that are missing."""
    for section in sections:
        if not settings.has_section(section):
            settings.add_section(section)


def write_ppsspp_config(system: Emulator) -> None:
    """Update ppsspp.ini for the game."""
    settings = CaseSensitiveConfigParser(interpolation=None)
    if _PPSSPP_INI.exists():
        try:
            settings.read(_PPSSPP_INI, encoding="utf_8_sig")
        except (OSError, UnicodeDecodeError, configparser.Error):
            pass  # an unreadable file is rewritten from scratch

    create_ppsspp_config(settings, system)
    with ensure_parents_and_open(_PPSSPP_INI, "w") as config_file:
        settings.write(config_file)


def _write_retroachievements_token(token: str) -> None:
    """Save the RetroAchievements token, if there is one."""
    if token:
        with ensure_parents_and_open(_RETROACHIEVEMENTS_TOKEN, "w") as token_file:
            token_file.write(token)


def _configure_backend(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the graphics API and, for Vulkan, the GPU it runs on."""
    backend = resolve_gfx_backend(config)
    settings.set("Graphics", "GraphicsBackend", backend)
    if backend != BACKEND_VULKAN:
        return

    _logger.debug("Vulkan driver is available on the system.")
    if discrete_name := discrete_gpu_property("PPSSPP", "Name", vulkan.get_discrete_gpu_name):
        settings.set("Graphics", "VulkanDevice", discrete_name)


def _configure_graphics(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the [Graphics] section."""
    _configure_backend(settings, config)

    options = {
        "InternalResolution": config.get_str("internal_resolution", "1"),
        "SoftwareRenderer": "False",  # always false
        "FullScreen": "True",  # always fullscreen
        "VSync": _bool(config, "vsync"),
        "FrameSkip": config.get_str("frameskip", "0"),
        "FrameSkipType": "0",  # a number of frames, not a percent
        "AutoFrameSkip": _bool(config, "autoframeskip"),
        "SkipBufferEffects": _bool(config, "skip_buffer_effects"),
        "DisableRangeCulling": _bool(config, "disable_culling"),
        "SkipGPUReadbackMode": config.get_str("skip_gpu_readbacks", "0"),
        "TextureBackoffCache": _bool(config, "lazy_texture_caching"),
        "SplineBezierQuality": config.get_str("curves_quality", "2"),
        "RenderDuplicateFrames": _bool(config, "duplicate_frames"),
        "InflightFrames": config.get_str("buffer_graphics", "3"),
        "HardwareTransform": "True",  # always true
        "SoftwareSkinning": _bool(config, "software_skinning", True),
        "HardwareTessellation": _bool(config, "hardware_tessellation"),
        "TexScalingType": config.get_str("texture_scaling_type", "0"),
        "TexScalingLevel": config.get_str("texture_scaling_level", "1"),
        "TexDeposterize": _bool(config, "texture_deposterize"),
        "AnisotropyLevel": config.get_str("anisotropic_filtering", "4"),
        "TextureFiltering": config.get_str("texture_filtering", "1"),
        "Smart2DTexFiltering": _bool(config, "smart_2d"),
        # the FPS counter is the global "display_fps" option of the menu
        "ShowFPSCounter": (
            _FPS_COUNTER_BOTH
            if config.get_bool("display_fps") or config.get_bool("show_fps")
            else "0"
        ),
        "DisplayIntegerScale": "False",
    }
    for option, value in options.items():
        settings.set("Graphics", option, value)


def _configure_sound(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the game volume that corresponds to the audio gain of the game, if it has one.

    The menu does not offer the gain for PPSSPP at the moment: without it the
    volume the user set in PPSSPP's own UI stays.
    """
    gain = config.get("ppsspp_audio_gain")
    if gain is config.MISSING:
        return
    # PPSSPP cannot amplify, so 0 dB is the loudest: a positive gain is the same as 0 dB
    settings.set("Sound", "GameVolume", str(gain_to_percent(gain, _MAX_VOLUME)))


def _configure_system_param(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write [SystemParam]: the nickname and the save options."""
    # Forcing the nickname to the user name, or to the RetroAchievements one
    username = getpass.getuser()
    if config.get_bool("retroachievements") and (
        config_username := config.get("retroachievements.username")
    ):
        username = config_username
    settings.set("SystemParam", "NickName", username)
    # Do not encrypt saves, so they can be exchanged between machines
    settings.set("SystemParam", "EncryptSave", "False")
    settings.set("SystemParam", "MemStickSize", "32")  # 32 GB memory stick


def _configure_general(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write [General]: first run, rewind, cheats, save state slot and Discord."""
    settings.set("General", "FirstRun", "False")
    settings.set(
        "General",
        "RewindFlipFrequency",
        config.get_bool("rewind", return_values=(_REWIND_EVERY_5_SECONDS, "0")),
    )
    settings.set("General", "EnableCheats", _bool(config, "enable_cheats"))
    settings.set("General", "CheckForNewVersion", "False")
    settings.set("General", "StateSlot", config.get_str("state_slot", "0"))
    settings.set(
        "General",
        "DiscordRichPresence",
        config.get_bool("discordrpc", False, return_values=("1", "0")),
    )


def _configure_achievements(settings: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write [Achievements]."""
    if not config.get_bool("retroachievements"):
        settings.set("Achievements", "AchievementsEnable", "False")
        settings.set("Achievements", "AchievementsChallengeMode", "False")
        return

    settings.set(
        "Achievements", "AchievementsUserName", config.get_str("retroachievements.username", "")
    )
    settings.set(
        "Achievements", "AchievementsChallengeMode", _bool(config, "retroachievements.hardcore")
    )
    settings.set(
        "Achievements", "AchievementsEncoreMode", _bool(config, "retroachievements.encore")
    )
    settings.set(
        "Achievements", "AchievementsUnofficial", _bool(config, "retroachievements.unofficial")
    )
    settings.set("Achievements", "AchievementsSoundEffects", "True")
    settings.set("Achievements", "AchievementsEnable", "True")
    _write_retroachievements_token(config.get_str("retroachievements.token", ""))


def create_ppsspp_config(settings: CaseSensitiveConfigParser, system: Emulator) -> None:
    """Fill the settings of ppsspp.ini for the game."""
    config = system.config
    _ensure_sections(
        settings, "Graphics", "Sound", "SystemParam", "General", "Upgrade", "Achievements"
    )

    _configure_graphics(settings, config)
    _configure_sound(settings, config)
    _configure_system_param(settings, config)
    _configure_general(settings, config)

    # don't upgrade
    for option in ("UpgradeMessage", "UpgradeVersion", "DismissedVersion"):
        settings.set("Upgrade", option, "")

    _configure_achievements(settings, config)

    # Custom: the user can configure PPSSPP directly with lines like ppsspp.section.option=value
    for section_option, user_value in config.items(starts_with="ppsspp."):
        section, _, option = section_option.partition(".")
        _ensure_sections(settings, section)
        settings.set(section, option, str(user_value))
