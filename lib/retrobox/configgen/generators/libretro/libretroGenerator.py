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
from retrobox.configgen.generators.libretro import (
    libretro_hotkeys,
    libretroConfig,
    libretroControllers,
)
from retrobox.configgen.generators.libretro.libretroPaths import (
    _RETROARCH_BIN,
    _RETROARCH_CFGDIR,
    _RETROARCH_XDG,
    RETROARCH_CFG,
    RETROARCH_CORES,
    RETROARCH_SHADERS,
    RETROARCH_SHARE,
)
from retrobox.configgen.utils import videoMode, vulkan
from retrobox.configgen.hotkeys import load_table
from retrobox.configgen.utils.bezel_policy import configured_bezel
from retrobox.paths import (
    OVERLAYS,
    RETROARCH_COMMANDS,
    SAVES,
    _SHADERS_DIR,
    configure_emulator,
    mkdir_if_not_exists,
)

if TYPE_CHECKING:
    from retrobox.configgen.Emulator import Emulator

_logger = logging.getLogger(__name__)

_GL_BACKENDS = ("gl", "glcore")
# video drivers, best first: an unavailable one falls back to the next ones
_BACKEND_ORDER = ("vulkan", "glcore", "gl")
_BACKEND_ALIASES = {"opengl": "gl"}
_MIN_GLCORE_VERSION = 3.1
_GLCORE_VENDORS = ("nvidia", "amd")
# cores whose hardware renderer needs an OpenGL context: without a driver
# chosen, they start the cascade at glcore / gl instead of vulkan
_FORCE_GLCORE_CORES = ("kronos", "mupen64plus_next", "melonds", "beetle-psx-hw")
_FORCE_GL_CORES = ("parallel_n64", "yabasanshiro", "boom3")
_AUTO_STATE_SUFFIX = ".auto"
_AUTO_BACKEND = "auto"


def _resolve_shader(system: Emulator, rom: Path, gfx_backend: str) -> tuple[Path | None, bool]:
    """Find the video shader of the game.

    Returns:
        The shader path, and whether it is a "noBezel" shader, which draws the
        bezel itself. (None, False) when the game has no shader, or when its
        shader is installed nowhere: then no shader is loaded at all.
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

    if not isinstance(game_shader, str) or game_shader.strip() in ("", "none"):
        return None, False

    shader_type = "slang" if gfx_backend in ("glcore", "vulkan") else "glsl"
    shader_filename = f"{game_shader.strip()}.{shader_type}p"
    candidates = (
        _SHADERS_DIR,
        RETROARCH_SHADERS / f"shaders_{shader_type}",
        RETROARCH_SHADERS,
    )
    video_shader = next(
        (directory / shader_filename for directory in candidates
         if (directory / shader_filename).is_file()),
        None,
    )
    if video_shader is None:
        _logger.warning(
            "Shader %s not found in %s; no shader loaded",
            shader_filename, ", ".join(str(directory) for directory in candidates),
        )
        return None, False
    _logger.debug("shader: %s", video_shader)
    return video_shader, "noBezel" in video_shader.name


def _backend_available(backend: str) -> bool:
    """Whether RetroArch can use the video driver ``backend`` here."""
    if backend == "vulkan":
        return vulkan.is_available()
    if backend == "glcore":
        return (
            videoMode.getGLVendor() in _GLCORE_VENDORS
            and videoMode.getGLVersion() >= _MIN_GLCORE_VERSION
        )
    return True  # gl


def _first_available(start: str) -> str:
    """``start`` if it is available, else the next one of _BACKEND_ORDER that is."""
    for backend in _BACKEND_ORDER[_BACKEND_ORDER.index(start):]:
        if _backend_available(backend):
            return backend
    return _BACKEND_ORDER[-1]


def _requested_backend(system: Emulator) -> str | None:
    """The video driver chosen for the game ("gfxbackend"), if any.

    retroarch.cfg is not looked at: its video_driver is written by this very
    generator on every launch, so it would only echo the previous choice.
    """
    chosen = system.config.get_str("gfxbackend", "")
    chosen = _BACKEND_ALIASES.get(chosen.strip().lower(), chosen.strip().lower())
    if not chosen or chosen == _AUTO_BACKEND:
        return None
    if chosen not in _BACKEND_ORDER:
        _logger.warning("unknown video driver %r, choosing one automatically", chosen)
        return None
    return chosen


def gfx_backend_get(system: Emulator) -> str:
    """Return the video driver to use: "vulkan", "glcore" or "gl".

    The driver chosen for the game, or else the best one for its core
    (vulkan, except for the cores that need OpenGL), falling back in the
    order vulkan > glcore > gl when it isn't available. Shader presets need
    vulkan or glcore (.slangp); gl only runs .glslp ones.
    """
    start = _requested_backend(system)
    if start is None:
        core = system.config.core
        if core in _FORCE_GL_CORES:
            start = "gl"
        elif core in _FORCE_GLCORE_CORES:
            start = "glcore"
        else:
            start = _BACKEND_ORDER[0]
    backend = _first_available(start)
    if backend != start:
        _logger.info("video driver %s not available, using %s", start, backend)
    _logger.debug("video driver: %s", backend)
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

    def hotkey_bindings(self, system):
        """RetroArch reads most hotkeys itself (see libretro_hotkeys)."""
        return libretro_hotkeys.bindings(load_table())

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
                    configured_bezel(system.config), shader_bezel, gfx_backend, video_shader
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

        return Command.Command(
            array=command_wrapper,
            env={"XDG_CONFIG_HOME": _RETROARCH_XDG},
            stdin_fifo=RETROARCH_COMMANDS,
        )

    def savestates(self, system: Emulator, rom: Path) -> dict[str, object] | None:
        """RetroArch's states, by slot: ``<saves>/<rom's folder>/<rom name>.state<N>``.

        The folder follows ``sort_savestates_by_content_enable``; the overlay
        asks for them through the command pipe (``stdin_cmd_enable``).
        """
        if configure_emulator(rom):
            return None
        try:
            slot = int(system.config.get_str("state_slot") or 0)
        except ValueError:
            slot = 0
        return {
            "control": str(RETROARCH_COMMANDS),
            "dir": str(SAVES / rom.parent.name),
            "name": rom.stem,
            "slot": slot,
        }

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
