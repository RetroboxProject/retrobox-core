"""Building blocks of the MAME command line (everything but the game itself)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import (
    _DECORATIONS_DEF_DIR,
    _DECORATIONS_DIR,
    BIOS,
    MAME_ARTWORK_DIR,
    MAME_SOFTWARE_DIR,
    SCREENSHOTS,
    mkdir_if_not_exists,
)

from ...utils import videoMode
from .mame_game import SUBDIR_SOFT_LISTS
from .mamePaths import MAME_BIOS, MAME_CHEATS, MAME_CONFIG, MAME_ROMS, MAME_SAVES

if TYPE_CHECKING:
    from ...typedefs import Resolution
    from ...Emulator import Emulator
    from .mame_game import MameGame

CommandLine = list[str | Path]

MAME_BIN = "/usr/bin/mame/mame"
_MAME_DIR = "/usr/bin/mame"
_ROTATIONS = ("autoror", "autorol")
_POINTER_OPTIONS = (
    "-dial_device",
    "-trackball_device",
    "-paddle_device",
    "-positional_device",
    "-mouse_device",
)


@dataclass(frozen=True)
class InputOptions:
    """The mouse and gun options, and what mameControllers needs to know about them."""

    arguments: CommandLine
    use_mouse: bool
    multi_mouse: bool


def userdata_directories() -> list[Path]:
    """Return the folders MAME needs to exist."""
    return [
        MAME_CONFIG,
        MAME_SAVES / "nvram",
        MAME_SAVES / "cfg",
        MAME_SAVES / "input",
        MAME_SAVES / "state",
        MAME_SAVES / "diff",
        MAME_SAVES / "comments",
        MAME_BIOS / "artwork" / "crosshairs",
        MAME_CHEATS,
        MAME_SAVES / "plugins",
        MAME_CONFIG / "ctrlr",
        MAME_CONFIG / "ini",
    ]


def _rom_path(game: MameGame) -> str:
    """Return the "-rompath" value: where MAME looks for roms and bioses."""
    paths = [f"{game.rom.parent}", f"{MAME_BIOS}", f"{BIOS}"]
    if game.mess is not None:
        paths.append(f"{MAME_ROMS}")
        if game.soft_list in SUBDIR_SOFT_LISTS:
            paths.append(f"{MAME_SOFTWARE_DIR}")
    return ";".join(paths)


def base_options(game: MameGame) -> CommandLine:
    """Sound, search paths, cheats and logging, the same for every game.

    MAME options used here are explained as it's not always straightforward. A
    lot more options can be configured, just run ``mame -showusage``.
    """
    art_path = (
        f"{MAME_ARTWORK_DIR}/;/usr/bin/mame/artwork/;{MAME_BIOS / 'artwork'};"
        f"{_DECORATIONS_DEF_DIR};{_DECORATIONS_DIR}"  # first for systems ; second for overlays
    )
    return [
        "-sound", "pipewire",  # fixes audio from 0.278
        "-skip_gameinfo",  # skip game info at start
        "-rompath", _rom_path(game),
        # MAME various paths we can probably do better
        "-bgfx_path", "/usr/bin/mame/bgfx/",  # core bgfx files can be left on ROM filesystem
        "-fontpath", "/usr/bin/mame/",  # fonts can be left on ROM filesystem
        "-languagepath", "/usr/bin/mame/language/",  # translations can be left on ROM filesystem
        "-pluginspath", f"/usr/bin/mame/plugins/;{MAME_SAVES / 'plugins'}",
        "-samplepath", MAME_BIOS / "samples",  # current storage location for MAME samples
        "-artpath", art_path,
        "-cheat",  # enable cheats
        "-cheatpath", MAME_CHEATS,  # should point to the path containing the cheat.7z file
        "-verbose",  # logs and Switchres ini read by default (including its own verbose)
        "-switchres_ini",
        # MAME saves a lot of stuff, we need to map this on <saves>/mame/<subfolder>
        "-nvram_directory", MAME_SAVES / "nvram",
    ]


def config_directory(game: MameGame) -> Path:
    """Create and return the folder where MAME keeps the config of the game.

    It is the default one, a custom one if the option is selected, or one per
    game for MESS systems that may need additional config.
    """
    system = game.system
    custom = system.config.get_bool("customcfg")
    base_path = MAME_CONFIG if game.mess is None else MAME_CONFIG / game.mess.sys_name
    mkdir_if_not_exists(base_path)
    cfg_path = base_path / "custom" if custom else base_path
    mkdir_if_not_exists(cfg_path)

    # MAME creates custom configs per game for MAME ROMs and MESS ROMs with no
    # system attached (LCD games, TV games, etc.). This allows an alternate
    # config path per game for MESS console/computer ROMs.
    if system.config.get_bool("pergamecfg") and game.has_machine:
        cfg_path = base_path / game.rom.name
        mkdir_if_not_exists(cfg_path)
    return cfg_path


def directory_options(game: MameGame, cfg_path: Path) -> CommandLine:
    """Folders MAME reads and writes, and the software list ones."""
    cmd: CommandLine = [
        "-cfg_directory", cfg_path,
        "-input_directory", MAME_SAVES / "input",
        "-state_directory", MAME_SAVES / "state",
        "-snapshot_directory", SCREENSHOTS,
        "-diff_directory", MAME_SAVES / "diff",
        "-comment_directory", MAME_SAVES / "comments",
        "-homepath", MAME_SAVES / "plugins",
        "-ctrlrpath", MAME_CONFIG / "ctrlr",
        "-inipath", f"{MAME_CONFIG};{MAME_CONFIG / 'ini'}",
        "-crosshairpath", MAME_BIOS / "artwork" / "crosshairs",
    ]
    if game.soft_list != "":
        cmd += ["-swpath", MAME_SOFTWARE_DIR, "-hashpath", MAME_SOFTWARE_DIR / "hash"]
    return cmd


def _video_engine_options(system: Emulator) -> CommandLine:
    """Video engine: https://docs.mamedev.org/advanced/bgfx.html"""
    video = system.config.get("video")
    if video == "bgfx":
        backend = system.config.get("bgfxbackend", "automatic")
        return [
            "-video", "bgfx",
            "-bgfx_backend", "auto" if backend == "automatic" else backend,
            "-bgfx_screen_chains", system.config.get("bgfxshaders", "default"),
        ]
    if video == "accel":
        return ["-video", "accel"]
    return ["-video", "auto"]


def video_options(system: Emulator, resolution: Resolution) -> CommandLine:
    """Video engine, resolution, sync, rotation and artwork options."""
    config = system.config
    cmd = _video_engine_options(system)

    # CRT / SwitchRes support
    if config.get_bool("switchres"):
        cmd += ["-modeline_generation", "-changeres", "-modesetting", "-readconfig"]
    else:
        cmd += ["-resolution", f"{resolution['width']}x{resolution['height']}"]

    # Refresh rate options to help with screen tearing. syncrefresh is unlisted:
    # it requires specific display timings and 99.9% of users will get
    # unplayable games. It is left so it can be set manually, for CRT or other
    # arcade-specific display users.
    if config.get_bool("vsync"):
        cmd.append("-waitvsync")
    if config.get_bool("syncrefresh"):
        cmd.append("-syncrefresh")

    # Rotation / TATE options
    if (rotation := config.get("rotation")) in _ROTATIONS:
        cmd.append(f"-{rotation}")

    if config.get_bool("artworkcrop"):
        cmd.append("-artwork_crop")

    # UI enable: for computer systems, the default sends all keys to the emulated
    # system. This enables hotkeys, but some keys may pass through to MAME and
    # not be usable in the emulated system. Hotkey + D-Pad Up toggles this when
    # in use (scroll lock key)
    if config.get_bool("enableui", True):
        cmd.append("-ui_active")
    return cmd


def plugin_options(system: Emulator) -> CommandLine:
    """Load the selected plugins."""
    config = system.config
    plugins = []
    if config.get_bool("hiscoreplugin", True):
        plugins.append("hiscore")
    if config.get_bool("coindropplugin"):
        plugins.append("coindrop")
    if config.get_bool("dataplugin"):
        plugins.append("data")
    if config.get_bool("offscreenreload"):  # for light guns games
        plugins.append("offscreenreload")
    return ["-plugins", "-plugin", ",".join(plugins)] if plugins else []


def input_options(game: MameGame) -> InputOptions:
    """Mouse, joystick and lightgun device options."""
    system = game.system
    use_guns = system.config.use_guns
    use_mouse = system.config.get_bool("use_mouse") or game.has_machine
    device = "mouse" if use_mouse else "joystick"

    cmd: CommandLine = []
    for option in _POINTER_OPTIONS:
        cmd += [option, device]
    if use_mouse:
        cmd.append("-ui_mouse")
    if not use_guns:
        cmd += ["-lightgun_device", device, "-adstick_device", device]

    # Multimouse option currently hidden in ES, SDL only detects one mouse.
    # Leaving code intact for testing & possible ManyMouse integration
    multi_mouse = system.config.get_bool("multimouse")
    if multi_mouse:
        cmd.append("-multimouse")

    if use_guns:
        cmd += ["-lightgunprovider", "udev", "-lightgun_device", "lightgun"]
        cmd += ["-adstick_device", "lightgun"]

    return InputOptions(cmd, use_mouse, multi_mouse)


def screen_options(system: Emulator) -> CommandLine:
    """Number of screens, when more than one is used."""
    if system.config.get_bool("multiscreens"):
        screens = videoMode.getScreensInfos(system.config)
        if len(screens) > 1:
            return ["-numscreens", str(len(screens))]
    return []


def working_directory() -> str:
    """Return the MAME folder (it lets the data plugin load properly)."""
    return _MAME_DIR
