from __future__ import annotations

from typing import TYPE_CHECKING

from ..Generator import Generator
from .dosbox_paths import DOSBOX_BIN, DOSBOX_CFG
from ...utils.configparser import CaseSensitiveConfigParser

from ... import Command

if TYPE_CHECKING:
    from pathlib import Path

    from ...typedefs import HotkeysContext


class DosBoxGenerator(Generator):

    # Main entry of the module
    # Return command
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        
        # Find rom path
        game_bat_file = rom / "dosbox.bat"
        game_cfg_file = rom / "dosbox.cfg"

        # configuration file
        ini_settings = CaseSensitiveConfigParser(interpolation=None)

        if DOSBOX_CFG.exists():
            ini_settings.read(DOSBOX_CFG)

        # section sdl
        if not ini_settings.has_section("sdl"):
            ini_settings.add_section("sdl")
        ini_settings.set("sdl", "output", "opengl")

        # section cpu
        if not ini_settings.has_section("cpu"):
            ini_settings.add_section("cpu")

        ini_settings.set("cpu", "core", system.config.get("dosbox_cpu_core", "auto"))
        ini_settings.set("cpu", "cputype", system.config.get("dosbox_cpu_cputype", "auto"))
        ini_settings.set("cpu", "cycles", system.config.get("dosbox_cpu_cycles", "auto"))

        # save
        with DOSBOX_CFG.open('w') as config:
            ini_settings.write(config)

        commandArray: list[str | Path] = [
            DOSBOX_BIN,
            "-fullscreen",
            # This loads _CONFIG_DIR / dosbox.conf
            "-userconf",
            "-exit",
            game_bat_file,
            "-c", f"""set ROOT={rom}""",
        ]

        if game_cfg_file.exists():
            # Then load gameConfFile if it exists
            commandArray.extend(['-conf', game_cfg_file])

        commandArray.extend([
            # Then load _CUSTOM_CONFIG after all the others
            "-conf", DOSBOX_CFG
        ])

        return Command.Command(array=commandArray)

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "dosbox",
            "keys": { "exit": ["KEY_LEFTCTRL", "KEY_F9"] }
        }
