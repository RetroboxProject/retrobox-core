from __future__ import annotations

from typing import TYPE_CHECKING

from retrobox.configgen import Command
from retrobox.configgen.controller import generate_sdl_game_controller_config, write_sdl_controller_db
from retrobox.configgen.generators.Generator import Generator
from retrobox.paths import EMULATORS


if TYPE_CHECKING:
    from retrobox.configgen.typedefs import HotkeysContext

class ShGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "shell",
            "keys": { "exit": ["KEY_LEFTALT", "KEY_F4"] }
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        # in case of squashfs, the root directory is passed
        runsh = rom / "run.sh"
        shrom = runsh if runsh.exists() else rom

        # PortMaster uses this.
        write_sdl_controller_db(playersControllers)

        command_array = ["/bin/bash", shrom]
        return Command.Command(array=command_array,env={
            #"XDG_CONFIG_HOME": EMULATORS,
            "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers)
        })

    def getMouseMode(self, config, rom):
        return True
