"""Generator of the Mupen64Plus command (the Nintendo 64, with a standalone emulator)."""

from __future__ import annotations

import configparser
from typing import TYPE_CHECKING, Final

from retrobox.configgen import Command
from retrobox.configgen.hotkeys import CLOSE_WINDOW, HotkeyAction
from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser
from retrobox.paths import (
    SCREENSHOTS,
    configure_emulator,
    ensure_parents_and_open,
    mkdir_if_not_exists,
)

from ..Generator import Generator
from . import mupen64plus_config, mupen64plus_controllers
from .mupen64plus_paths import (
    MUPEN64PLUS,
    MUPEN64PLUS_CONFIG,
    MUPEN64PLUS_CONFIG_DIR,
    MUPEN64PLUS_SAVES,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ...config import SystemConfig
    from ...controller import Controllers
    from ...typedefs import Resolution

_CORE_LIBRARY: Final = "libmupen64plus.so.2.0.0"

# the plugins every game uses, whatever its core: (option of the command, plugin)
_COMMON_PLUGINS: Final = (
    ("--audio", "audio-sdl"),
    ("--input", "input-sdl"),
    ("--rsp", "rsp-hle"),
)


def _data_dir(prefix: Path) -> Path:
    """Return the folder with the data of Mupen64Plus (its ROM database and its cheats)."""
    return prefix / "share" / "mupen64plus"


def _read_settings() -> CaseSensitiveConfigParser:
    """Return the settings Mupen64Plus left in its file, or none if they cannot be read."""
    ini = CaseSensitiveConfigParser(interpolation=None)
    if MUPEN64PLUS_CONFIG.exists():
        try:
            ini.read(MUPEN64PLUS_CONFIG, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError):
            # give up the file: it is written again below
            return CaseSensitiveConfigParser(interpolation=None)
    return ini


def _write_settings(
    config: SystemConfig,
    players_controllers: Controllers,
    resolution: Resolution,
    data_dir: Path,
) -> None:
    """Write mupen64plus.cfg: the options of the game and the mapping of the controllers."""
    ini = _read_settings()
    mupen64plus_config.write_config(ini, config, resolution, data_dir)
    mupen64plus_controllers.write_controllers(ini, config, players_controllers)
    with ensure_parents_and_open(MUPEN64PLUS_CONFIG, "w") as handle:
        ini.write(handle)


def _build_command(mupen: Path, config: SystemConfig, rom: Path) -> list[str]:
    """Return the command line that starts the game, with every file given by its path."""
    prefix = MUPEN64PLUS.prefix_of(mupen)
    plugins = prefix / "lib" / "mupen64plus"
    command = [
        str(mupen),
        "--corelib",
        str(prefix / "lib" / _CORE_LIBRARY),
        "--plugindir",
        str(plugins),
        "--datadir",
        str(_data_dir(prefix)),
        "--configdir",
        str(MUPEN64PLUS_CONFIG_DIR),
    ]
    video = mupen64plus_config.VIDEO_PLUGINS[mupen64plus_config.core_name(config)]
    for option, plugin in (("--gfx", video), *_COMMON_PLUGINS):
        command.extend((option, str(plugins / f"mupen64plus-{plugin}.so")))
    command.append("--fullscreen")
    # cheats given by hand, in the syntax of the --cheats option
    if cheats := config.get_str("mupen64plus_cheats"):
        command.extend(("--cheats", cheats))
    if not configure_emulator(rom):
        command.append(str(rom))
    return command


class Mupen64PlusGenerator(Generator):
    """Generates the Mupen64Plus command and its settings."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def hotkey_bindings(self, system):
        """Hotkey+Start closes the window (Alt+F4), so Mupen64Plus quits cleanly."""
        return {HotkeyAction.EXIT: CLOSE_WINDOW}

    def usesOpenGLDirectPreload(self, config) -> bool:
        """MangoHud is preloaded: every video plugin draws with OpenGL."""
        return True

    def getInGameRatio(self, config, gameResolution, rom) -> float:
        """Return the aspect ratio of the picture, the one set in the options."""
        return 16 / 9 if mupen64plus_config.aspect_ratio(config) == "16/9" else 4 / 3

    # the signature is fixed by the Generator interface
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def generate(
        self,
        system,
        rom,
        playersControllers,  # name fixed by the Generator interface
        metadata,
        guns,
        wheels,
        gameResolution,  # name fixed by the Generator interface
    ):
        """Write mupen64plus.cfg and return the command that starts Mupen64Plus."""
        mupen = MUPEN64PLUS.require()
        data_dir = _data_dir(MUPEN64PLUS.prefix_of(mupen))
        self.check_if_exists(data_dir, system.config.emulator)
        for directory in (MUPEN64PLUS_CONFIG_DIR, MUPEN64PLUS_SAVES, SCREENSHOTS):
            mkdir_if_not_exists(directory)
        _write_settings(system.config, playersControllers, gameResolution, data_dir)
        env = {"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1"}
        return Command.Command(array=_build_command(mupen, system.config, rom), env=env)
