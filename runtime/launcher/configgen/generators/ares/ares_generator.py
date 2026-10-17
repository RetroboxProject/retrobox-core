"""Generator of the Ares command (a multi-system accuracy emulator)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from runtime.launcher.configgen import Command
from runtime.paths import SCREENSHOTS, configure_emulator, mkdir_if_not_exists

from ..Generator import Generator
from . import ares_config
from .ares_paths import (
    _ARES_CFGDIR,
    _ARES_LIBDIR,
    _ARES_SAVES,
    _ARES_SHADERS_DIR,
    _ARES_SHARE,
    _ARES_XDG,
    ARES_BIN,
)
from .ares_systems import ares_system_name

if TYPE_CHECKING:
    from ...config import SystemConfig


class AresGenerator(Generator):
    """Generates the Ares command and its settings."""

    # the method names are fixed by the Generator interface
    # pylint: disable=invalid-name

    def usesOpenGLDirectPreload(self, config) -> bool:
        """MangoHud is preloaded when Ares draws with OpenGL (its only driver on Linux)."""
        return "OpenGL" in ares_config.video_driver(config)

    def allows_bezel(self, config: SystemConfig) -> bool:
        """A picture stretched to the window, or widened to 16:9, leaves no room for a bezel."""
        return (
            ares_config.output_mode(config) != ares_config.OUTPUT_STRETCH
            and ares_config.aspect_correction(config) != ares_config.ASPECT_ANAMORPHIC
        )

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
        """Write settings.bml and return the command that starts Ares."""
        self.check_if_exists(ARES_BIN, system.config.emulator)
        self.check_if_exists(_ARES_SHARE, system.config.emulator)

        # make sure the config and save folders exist
        mkdir_if_not_exists(_ARES_CFGDIR)
        mkdir_if_not_exists(_ARES_SAVES / system.name)
        mkdir_if_not_exists(SCREENSHOTS)

        # write settings.bml before starting
        ares_config.write_ares_config(system, playersControllers)

        command_array = [str(ARES_BIN)]
        args_array: list[str] = []

        # the shader must be loaded from the command line
        shader_cfg = system.renderconfig.get("shader")
        if ares_config.resolve_shader(shader_cfg, _ARES_SHADERS_DIR) != "None":
            args_array = ["--shader", shader_cfg]

        # systems that share file extensions are told apart by name
        if ares_system := ares_system_name(system.name):
            args_array.extend(["--system", ares_system])

        # kiosk mode disables the bottom bar;
        # pseudofullscreen allows for better window management on KDE
        args_array.extend(["--kiosk", "--pseudofullscreen"])

        if not configure_emulator(rom):
            args_array.append(str(rom))
            command_array.extend(args_array)

        env = {
            "XDG_DATA_HOME": str(_ARES_XDG),
            "XDG_CONFIG_HOME": str(_ARES_XDG),
            "LD_LIBRARY_PATH": str(_ARES_LIBDIR),
        }
        return Command.Command(array=command_array, env=env)
