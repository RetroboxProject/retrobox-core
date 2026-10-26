from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from ... import Command
from ...controller import generate_sdl_game_controller_config
from ...exceptions import RetroboxException
from ..Generator import Generator

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext

class HeroicGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "wine",
            # Es posible que necesites cambiar esto si "batocera-wine windows stop" 
            # ya no aplica para cerrar juegos lanzados nativamente por heroic.
            "keys": { "exit": "/usr/bin/batocera-wine windows stop" }
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        # Leer el contenido del archivo (el enlace de heroic, legendary, gog, etc.)
        try:
            with open(rom, 'r', encoding='utf-8') as f:
                enlace = f.read().strip()
        except Exception as e:
            raise RetroboxException(f"No se pudo leer el archivo de enlace: {e}")

        # Sustituir batocera-wine por heroic y pasarle el enlace leído
        commandArray = ["heroic", "--no-gui", enlace]

        environment: dict[str, str | Path] = {}
        
        try:
            language = subprocess.check_output("batocera-settings-get system.language", shell=True, text=True).strip()
        except subprocess.CalledProcessError:
            language = 'en_US'
            
        if language:
            environment.update({
                "LANG": language + ".UTF-8",
                "LC_ALL": language + ".UTF-8"
            })
            
        if system.config.get_bool("sdl_config", True):
            environment.update({
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
                "SDL_JOYSTICK_HIDAPI": "0"
            })

        return Command.Command(array=commandArray, env=environment)

    def getMouseMode(self, config, rom):
        return config.get_bool('force_mouse')