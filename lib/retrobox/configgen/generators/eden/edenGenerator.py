from __future__ import annotations

import logging
import os
from .eden_config import _eden_write_config
from ..Generator import Generator
from ... import Command
from retrobox.paths import DEFAULTS_DIR, SAVES, configure_emulator
from .edenPaths import _EDEN_INI, _EDEN_XDG, EDEN, setup_eden_environments

_logger = logging.getLogger(__name__)


class EdenGenerator(Generator):
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        _logger.warning("DEBUG: generate() llamado, emulator=%s", system.config['emulator'])
        emulator = system.config['emulator']

        # Create the folders and symlinks Eden needs
        setup_eden_environments()

        edenConfig = os.path.expanduser(_EDEN_INI)
        
        # The template still comes from the shipped data folder
        edenConfigTemplate = f'{DEFAULTS_DIR}/data/switch/qt-config.ini.template'
        _eden_write_config(edenConfig, edenConfigTemplate, system, playersControllers, emulator)

        commandArray = [str(EDEN.require())]

        if configure_emulator(rom):
            commandArray.extend(["-qlaunch"])
        else:
            commandArray.extend(["-f", "-g", str(rom)])

        environment = {
            "XDG_CONFIG_HOME":f"{_EDEN_XDG}",
            "XDG_DATA_HOME":f"{SAVES}/switch",
            # no HIDAPI: the button numbers of es_input.cfg are evdev's (see startup/run.py)
            "SDL_JOYSTICK_HIDAPI": "0",
        }

        return Command.Command(array=commandArray, env=environment)
    
