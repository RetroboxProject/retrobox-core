from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from .eden_config import _eden_write_config
from ..Generator import Generator
from ... import Command
from retrobox.paths import DEFAULTS_DIR, SAVES, configure_emulator
from .edenPaths import _EDEN_INI, _EDEN_XDG, EDEN_BIN, setup_eden_environments

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ...typedefs import HotkeysContext

class EdenGenerator(Generator):
    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "switch-emu",
            "keys": { "exit": ["KEY_LEFTALT", "KEY_F4"]}
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        _logger.warning("DEBUG: generate() llamado, emulator=%s", system.config['emulator'])
        emulator = system.config['emulator']

        # Invocar la creación modular de rutas y entornos symlink
        setup_eden_environments()

        edenConfig = os.path.expanduser(_EDEN_INI)
        
        # El template lo seguimos buscando en la carpeta del script
        edenConfigTemplate = f'{DEFAULTS_DIR}/data/switch/qt-config.ini.template'
        _eden_write_config(edenConfig, edenConfigTemplate, system, playersControllers, emulator)

        commandArray = [f"{EDEN_BIN}"]

        if configure_emulator(rom):
            commandArray.extend(["-qlaunch"])
        else:
            commandArray.extend(["-f", "-g", str(rom)])

        environment = {
            "XDG_CONFIG_HOME":f"{_EDEN_XDG}",
            "XDG_DATA_HOME":f"{SAVES}/switch",
            "SDL_JOYSTICK_HIDAPI": "1",
            "SDL_JOYSTICK_HIDAPI_STEAMDECK": "0",
            "SDL_JOYSTICK_HIDAPI_PS4": "1",
            "SDL_JOYSTICK_HIDAPI_PS5": "1",
            "SDL_JOYSTICK_HIDAPI_SWITCH": "1",
            "SDL_JOYSTICK_HIDAPI_XBOX": "1",
        }

        return Command.Command(array=commandArray, env=environment)
    

    def getMouseMode(self, config, rom):
        return True