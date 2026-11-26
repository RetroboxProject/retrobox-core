"""Settings of Mupen64Plus: all of its mupen64plus.cfg except for the controllers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from retrobox.configgen.hotkeys import HotkeyAction, Keys
from retrobox.paths import SCREENSHOTS

from .mupen64plus_paths import MUPEN64PLUS_SAVES

if TYPE_CHECKING:
    from pathlib import Path

    from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser

    from ...config import SystemConfig
    from ...typedefs import Resolution

DEFAULT_CORE: Final = "gliden64"

# the video plugin of each core, as it is named in its file (mupen64plus-<plugin>.so)
VIDEO_PLUGINS: Final = {
    "gliden64": "video-gliden64",
    "glide64mk2": "video-glide64mk2",
    "rice": "video-rice",
}

# the file of the installation that holds the settings version of the GLideN64 it built
GLIDEN64_VERSION_FILE: Final = "gliden64_config_version"

# primary buffer size, primary buffer target and secondary buffer size of Audio-SDL
_AUDIO_BUFFERS: Final = {
    "Very High": ("16384", "4096", "2048"),
    "High": ("16384", "2048", "1024"),
    "Medium": ("8192", "2048", "1024"),
    "Low": ("4096", "1024", "512"),
}
_DEFAULT_AUDIO_BUFFER: Final = "Medium"

# the frame skip Glide64mk2 may reach by itself, when it is left to decide
_AUTO_MAX_FRAMESKIP: Final = 5

# the joystick hotkeys of the core: Retrobox's input daemon handles the hotkeys
_JOYSTICK_HOTKEYS: Final = (
    "Joy Mapping Stop",
    "Joy Mapping Fullscreen",
    "Joy Mapping Save State",
    "Joy Mapping Load State",
    "Joy Mapping Increment Slot",
    "Joy Mapping Screenshot",
    "Joy Mapping Pause",
    "Joy Mapping Mute",
    "Joy Mapping Increase Volume",
    "Joy Mapping Decrease Volume",
    "Joy Mapping Fast Forward",
    "Joy Mapping Frame Advance",
    "Joy Mapping Gameshark",
)


def quote(value: str | Path) -> str:
    """Return ``value`` as mupen64plus.cfg stores a string."""
    return f'"{value}"'


def set_value(
    ini: CaseSensitiveConfigParser, section: str, key: str, value: object
) -> None:
    """Set a key of mupen64plus.cfg, creating its section if it is missing."""
    if not ini.has_section(section):
        ini.add_section(section)
    ini.set(section, key, str(value))


def core_name(config: SystemConfig) -> str:
    """Return the core of the game, which is its video plugin (GLideN64 if it is unknown)."""
    core = config.get_str("core", DEFAULT_CORE)
    return core if core in VIDEO_PLUGINS else DEFAULT_CORE


def aspect_ratio(config: SystemConfig) -> str:
    """Return the aspect ratio set for the game: ``16/9``, or ``4/3`` (the default)."""
    return "16/9" if config.get_str("mupen64plus_ratio", "4/3") == "16/9" else "4/3"


def _write_core(ini: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the paths and the options of the core."""
    section = "Core"
    # without its version Mupen64Plus drops the whole section
    set_value(ini, section, "Version", "1.01")
    set_value(ini, section, "ScreenshotPath", quote(SCREENSHOTS))
    set_value(ini, section, "SaveStatePath", quote(MUPEN64PLUS_SAVES))
    set_value(ini, section, "SaveSRAMPath", quote(MUPEN64PLUS_SAVES))
    # states and saves are named after the ROM file (a patch of batocera for the core)
    set_value(ini, section, "SaveFilenameFormat", "1000")
    # the 4 MB expansion pack
    set_value(ini, section, "DisableExtraMem", config.get_bool("mupen64plus_DisableExtraMem"))
    if slot := config.get_str("state_slot"):
        set_value(ini, section, "CurrentStateSlot", slot)
    autoincrement = config.get_bool("incrementalsavestates", True)
    set_value(ini, section, "AutoStateSlotIncrement", autoincrement)


# The keyboard hotkeys of the core that Retrobox's pad mapper presses (the overlay's
# menu does too): the action, the key of [CoreEvents] and the SDL keysym the core
# stores for it (the legacy SDL 1.2 value: F5 is 286), and the same key as evdev
# names it. They are written in every start, so that a mupen64plus.cfg of an older
# Mupen64Plus (or one edited by hand) cannot leave one of them on another key.
# The core has no key for the previous slot, and only advances (F6 here, which it
# leaves free) or takes a slot by number.
_KEYBOARD_HOTKEYS: Final = (
    (HotkeyAction.PAUSE, "Kbd Mapping Pause", 112, "KEY_P"),
    (HotkeyAction.SAVE_STATE, "Kbd Mapping Save State", 286, "KEY_F5"),
    (HotkeyAction.SLOT_NEXT, "Kbd Mapping Increment Slot", 287, "KEY_F6"),
    (HotkeyAction.LOAD_STATE, "Kbd Mapping Load State", 288, "KEY_F7"),
    (HotkeyAction.RESET, "Kbd Mapping Reset", 290, "KEY_F9"),
    # held while the pad's combination is: the core speeds up only while it is down
    (HotkeyAction.FAST_FORWARD, "Kbd Mapping Fast Forward", 102, "KEY_F"),
)


def hotkey_bindings() -> dict[HotkeyAction, Keys]:
    """The keys the pad mapper presses for each standard action Mupen64Plus can do."""
    return {action: Keys((evdev,)) for action, _key, _keysym, evdev in _KEYBOARD_HOTKEYS}


def _write_hotkeys(ini: CaseSensitiveConfigParser) -> None:
    """Write the keyboard hotkeys of the core."""
    for _action, key, keysym, _evdev in _KEYBOARD_HOTKEYS:
        set_value(ini, "CoreEvents", key, keysym)


def _clear_hotkeys(ini: CaseSensitiveConfigParser) -> None:
    """Empty the joystick hotkeys of the core, so a pad cannot trigger them by itself."""
    if not ini.has_section("CoreEvents"):
        return
    for key in _JOYSTICK_HOTKEYS:
        if ini.has_option("CoreEvents", key):
            ini.set("CoreEvents", key, quote(""))


def _write_audio(ini: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the options of the Audio-SDL plugin."""
    section = "Audio-SDL"
    choice = config.get_str("mupen64plus_AudioBuffer", _DEFAULT_AUDIO_BUFFER)
    sizes = _AUDIO_BUFFERS.get(choice, _AUDIO_BUFFERS[_DEFAULT_AUDIO_BUFFER])
    # the second limiter of the audio is off by default: it costs performance
    set_value(ini, section, "AUDIO_SYNC", config.get_bool("mupen64plus_AudioSync"))
    set_value(ini, section, "PRIMARY_BUFFER_SIZE", sizes[0])
    set_value(ini, section, "PRIMARY_BUFFER_TARGET", sizes[1])
    set_value(ini, section, "SECONDARY_BUFFER_SIZE", sizes[2])


def _write_video_general(ini: CaseSensitiveConfigParser, resolution: Resolution) -> None:
    """Write the window settings every video plugin reads."""
    section = "Video-General"
    # the sides are swapped when the screen is rotated
    width, height = sorted((resolution["width"], resolution["height"]), reverse=True)
    set_value(ini, section, "Fullscreen", True)
    set_value(ini, section, "ScreenWidth", width)
    set_value(ini, section, "ScreenHeight", height)
    set_value(ini, section, "VerticalSync", True)


def _write_gliden64(
    ini: CaseSensitiveConfigParser, config: SystemConfig, data_dir: Path
) -> None:
    """Write the options of the GLideN64 plugin."""
    section = "Video-GLideN64"
    # 0 is stretched, 1 forces 4:3 and 2 forces 16:9
    set_value(ini, section, "AspectRatio", 2 if aspect_ratio(config) == "16/9" else 1)
    # 0 renders at the resolution of the screen, the others at a multiple of the N64's
    native = config.get_str("mupen64plus_NativeResFactor", "0")
    set_value(ini, section, "UseNativeResolutionFactor", native)
    set_value(ini, section, "MultiSampling", config.get_str("mupen64plus_AntiAliasing", "0"))
    set_value(ini, section, "anisotropy", config.get_str("mupen64plus_Anisotropic", "0"))
    # the plugin resets its section when the version in it is not its own, and the
    # options with it: the installer leaves the version of the build in a file
    version_file = data_dir / GLIDEN64_VERSION_FILE
    if version_file.is_file():
        set_value(ini, section, "configVersion", version_file.read_text(encoding="utf-8").strip())


def _write_glide64mk2(ini: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the options of the Glide64mk2 plugin."""
    section = "Video-Glide64mk2"
    # 0 forces 4:3 and 1 forces 16:9
    set_value(ini, section, "aspect", 1 if aspect_ratio(config) == "16/9" else 0)
    set_value(ini, section, "fb_read_always", config.get_str("mupen64plus_fb_read_always", "-1"))
    anisotropic = config.get_str("mupen64plus_Anisotropic", "0") != "0"
    set_value(ini, section, "wrpAnisotropic", anisotropic)
    set_value(ini, section, "wrpAntiAliasing", config.get_str("mupen64plus_AntiAliasing", "0"))
    frameskip = config.get_str("mupen64plus_frameskip", "0")
    automatic = frameskip == "automatic"
    set_value(ini, section, "autoframeskip", automatic)
    set_value(ini, section, "maxframeskip", _AUTO_MAX_FRAMESKIP if automatic else frameskip)


def _write_rice(ini: CaseSensitiveConfigParser, config: SystemConfig) -> None:
    """Write the options of the Rice plugin."""
    section = "Video-Rice"
    set_value(ini, section, "Mipmapping", config.get_str("mupen64plus_Mipmapping", "0"))
    anisotropic = config.get_str("mupen64plus_Anisotropic", "0")
    set_value(ini, section, "AnisotropicFiltering", anisotropic)
    enhancement = config.get_str("mupen64plus_TextureEnhancement", "0")
    set_value(ini, section, "TextureEnhancement", enhancement)
    hires = config.get_bool("mupen64plus_LoadHiResTextures")
    set_value(ini, section, "LoadHiResTextures", hires)


def write_config(
    ini: CaseSensitiveConfigParser,
    config: SystemConfig,
    resolution: Resolution,
    data_dir: Path,
) -> None:
    """Write every section of mupen64plus.cfg but the controllers.

    Args:
        ini: The settings Mupen64Plus left in its file; what is not set here is kept.
        config: The configuration of the game.
        resolution: The resolution of the screen.
        data_dir: The ``share/mupen64plus`` folder of the installation.
    """
    _write_core(ini, config)
    _clear_hotkeys(ini)
    _write_hotkeys(ini)
    _write_audio(ini, config)
    _write_video_general(ini, resolution)
    core = core_name(config)
    if core == "glide64mk2":
        _write_glide64mk2(ini, config)
    elif core == "rice":
        _write_rice(ini, config)
    else:
        _write_gliden64(ini, config, data_dir)
