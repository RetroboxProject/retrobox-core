"""Generator of the RetroArch (libretro) command."""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.configgen import Command
from retrobox.configgen.Emulator import generate_bash_wrapper
from retrobox.configgen.exceptions import MissingCore
from retrobox.configgen.generators.Generator import Generator
from retrobox.configgen.generators.libretro import libretroConfig, libretroControllers
from retrobox.configgen.generators.libretro.libretroPaths import (
    _RETROARCH_BIN,
    _RETROARCH_CFGDIR,
    _RETROARCH_XDG,
    RETROARCH_CFG,
    RETROARCH_CORES,
    RETROARCH_SHADERS,
    RETROARCH_SHARE,
)
from retrobox.configgen.settings.unixSettings import UnixSettings
from retrobox.configgen.utils import videoMode, vulkan
from retrobox.configgen.utils.bezel_policy import configured_bezel
from retrobox.paths import OVERLAYS, _SHADERS_DIR, configure_emulator, mkdir_if_not_exists

if TYPE_CHECKING:
    from retrobox.configgen.typedefs import HotkeysContext
    from retrobox.configgen.Emulator import Emulator

_logger = logging.getLogger(__name__)

_GL_BACKENDS = ("gl", "glcore")
_MIN_GLCORE_VERSION = 3.1
_GLCORE_VENDORS = ("nvidia", "amd")
_FORCE_GLCORE_CORES = ("kronos", "mupen64plus_next", "melonds", "beetle-psx-hw")
_FORCE_GL_CORES = ("parallel_n64", "yabasanshiro", "boom3")
_AUTO_STATE_SUFFIX = ".auto"
_AUTO_BACKEND = "auto"


def _resolve_shader(system: Emulator, rom: Path, gfx_backend: str) -> tuple[Path | None, bool]:
    """Find the video shader of the game.

    Returns:
        The shader path (None if the game has no shader), and whether it is a
        "noBezel" shader, which draws the bezel itself.
    """
    render_config = system.renderconfig
    alt_decoration = videoMode.get_alt_decoration(system.name, rom, "retroarch")

    game_shader = None
    if alt_decoration == "0":
        game_shader = render_config.get("shader")
    elif f"shader-{alt_decoration}" in render_config:
        game_shader = render_config[f"shader-{alt_decoration}"]
    else:
        game_shader = render_config.get("shader")

    if "shader" not in render_config or game_shader is None:
        return None, False

    shader_type = "slang" if gfx_backend in ("glcore", "vulkan") else "glsl"
    shader_filename = f"{game_shader}.{shader_type}p"
    _logger.debug("searching shader %s", shader_filename)

    if (_SHADERS_DIR / shader_filename).exists():
        video_shader_dir = _SHADERS_DIR
    elif (RETROARCH_SHADERS / f"shaders_{shader_type}" / shader_filename).exists():
        video_shader_dir = RETROARCH_SHADERS / f"shaders_{shader_type}"
    else:
        video_shader_dir = RETROARCH_SHADERS

    video_shader = video_shader_dir / shader_filename
    return video_shader, "noBezel" in video_shader.name


def _gfx_backend_check(backend: str) -> str:
    """Return the requested video backend, or "gl" if it cannot be used."""
    if backend == "vulkan" and vulkan.is_available():
        return "vulkan"
    if (
        backend == "glcore"
        and videoMode.getGLVendor() in _GLCORE_VENDORS
        and videoMode.getGLVersion() >= _MIN_GLCORE_VERSION
    ):
        return "glcore"
    return "gl"


def _configured_backend() -> str | None:
    """Return the video backend set in retroarch.cfg, if any."""
    retroconfig = UnixSettings(RETROARCH_CFG, separator=" ")
    for option in ("video_driver", "gfxbackend"):
        backend = retroconfig.config.get("DEFAULT", option, fallback=None)
        if backend:
            backend = backend.strip("\"'")
        if backend:
            return backend
    return None


def _requested_backend(system: Emulator) -> str | None:
    """Return the video backend that was asked for, if any.

    The "gfxbackend" option of the game wins over the one of retroarch.cfg.
    """
    chosen = system.config.get_str("gfxbackend")
    if chosen and chosen != _AUTO_BACKEND:
        return chosen
    return _configured_backend()


def gfx_backend_get(system: Emulator) -> str:
    """Return the video backend to use: "gl", "glcore" or "vulkan".

    A backend that was asked for is used as it is (when the system supports it,
    else "gl"); otherwise "glcore" is the default, adjusted for some cores.
    """
    configured = _requested_backend(system)
    backend = _gfx_backend_check(configured or "glcore")
    if backend == "opengl":
        backend = "gl"

    if not configured and backend in _GL_BACKENDS:
        core = system.config.core
        if backend == "gl" and core in _FORCE_GLCORE_CORES:
            backend = "glcore"
        if backend == "glcore" and core in _FORCE_GL_CORES:
            backend = "gl"

    return backend


def _extra_config_files(system: Emulator, rom: Path) -> list[Path]:
    """Return the per-system, per-game and overlay configs appended to retroarch.cfg."""
    candidates = (
        _RETROARCH_CFGDIR / f"{system.name}.cfg",
        _RETROARCH_CFGDIR / system.name / f"{rom.name}.cfg",
        OVERLAYS / system.name / f"{rom.name}.cfg",
    )
    return [candidate for candidate in candidates if candidate.is_file()]


class LibretroGenerator(Generator):
    """Generates the RetroArch command and its configuration."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def supportsInternalBezels(self) -> bool:
        """RetroArch draws its own bezels (overlays), so MangoHud must not."""
        return True

    def usesOpenGLDirectPreload(self, config) -> bool:
        """Tell whether the emulator needs the OpenGL preload for MangoHud."""
        return config.get("gfxbackend") in _GL_BACKENDS

    def getHotkeysContext(self) -> HotkeysContext:
        """Return the RetroArch hotkeys."""
        return {
            "name": "retroarch",
            "keys": {
                "exit": ["KEY_LEFTSHIFT", "KEY_ESC"],
                "menu": ["KEY_LEFTSHIFT", "KEY_F1"],
                "pause": ["KEY_LEFTSHIFT", "KEY_P"],
                "coin": "KEY_F12",
                "save_state": ["KEY_LEFTSHIFT", "KEY_F3"],
                "restore_state": ["KEY_LEFTSHIFT", "KEY_F4"],
                "previous_slot": ["KEY_LEFTSHIFT", "KEY_F6"],
                "next_slot": ["KEY_LEFTSHIFT", "KEY_F5"],
                "rewind": ["KEY_LEFTSHIFT", "KEY_F11"],
                "fastforward": ["KEY_LEFTSHIFT", "KEY_F12"],
                "reset": ["KEY_LEFTSHIFT", "KEY_F10"],
                "translation": ["KEY_LEFTSHIFT", "KEY_F9"],
            },
        }

    # the signature is fixed by the Generator interface
    # pylint: disable-next=too-many-locals,too-many-arguments,too-many-positional-arguments
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
        self.check_if_exists(_RETROARCH_BIN, system.config.emulator)
        self.check_if_exists(RETROARCH_CORES, system.config.emulator)

        gfx_backend = gfx_backend_get(system)
        video_shader, shader_bezel = _resolve_shader(system, rom, gfx_backend)

        if "configfile" not in system.config:
            system.config["configfile"] = str(RETROARCH_CFG)
            launch = libretroConfig.LibretroLaunch(
                generator=self,
                system=system,
                rom=rom,
                resolution=gameResolution,
                metadata=metadata,
                inputs=libretroConfig.LibretroInputs(playersControllers, guns, wheels),
                # force_no_bezel and the bezel option are resolved by bezel_policy
                display=libretroConfig.LibretroDisplay(
                    configured_bezel(system.config), shader_bezel, gfx_backend
                ),
            )
            self._write_retroarch_cfg(launch)

        libretro_core = RETROARCH_CORES / f"{system.config.core}_libretro.so"
        info_file = RETROARCH_SHARE / f"{system.config.core}_libretro.info"

        dont_append_rom = configure_emulator(rom)
        if not info_file.exists() and not dont_append_rom:
            _logger.error("Core not found: %s", system.config.core)
            raise MissingCore

        args_array: list[str | Path] = ["--config", RETROARCH_CFG]
        if not dont_append_rom:
            args_array = ["-L", libretro_core, *args_array]

        if video_shader is not None:
            args_array.extend(["--set-shader", video_shader])

        if config_to_append := _extra_config_files(system, rom):
            args_array.extend(["--appendconfig", "|".join(str(path) for path in config_to_append)])

        if not dont_append_rom:
            args_array.append(rom)

        # load a savestate: a slot is given and it is not an automatic load
        state_slot = system.config.get_str("state_slot")
        if state_slot and not system.config.get("state_filename", _AUTO_STATE_SUFFIX).endswith(
            _AUTO_STATE_SUFFIX
        ):
            args_array.extend(["-e", state_slot])

        command_wrapper = [
            generate_bash_wrapper(system.config.emulator, _RETROARCH_BIN, args_array)
        ]

        return Command.Command(array=command_wrapper, env={"XDG_CONFIG_HOME": _RETROARCH_XDG})

    @staticmethod
    def _write_retroarch_cfg(launch: libretroConfig.LibretroLaunch) -> None:
        """Write retroarch.cfg: controllers, fixed paths and the game settings."""
        system = launch.system
        retroconfig = libretroConfig.open_unix_settings(RETROARCH_CFG)

        lightgun = True
        if "lightgun_map" in system.config:
            lightgun = system.config.get_bool("lightgun_map")
        libretroControllers.writeControllersConfig(
            retroconfig, system, launch.inputs.controllers, lightgun
        )
        libretroConfig.write_libretro_config_to_file(
            retroconfig, libretroConfig.rarch_custom_paths(system)
        )
        libretroConfig.write_libretro_config(retroconfig, launch)
        retroconfig.write()

        mkdir_if_not_exists(_RETROARCH_CFGDIR / "config" / "remaps" / "common")
