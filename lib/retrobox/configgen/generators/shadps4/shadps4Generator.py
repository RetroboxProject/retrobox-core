#
# This file is part of the batocera distribution (https://batocera.org).
# Copyright (c) 2025+.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# YOU MUST KEEP THIS HEADER AS IT IS
#
from __future__ import annotations

import getpass
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

import tomlkit

from retrobox.configgen.generators.shadps4.shadps4_paths import _SHADPS4_CFGDIR, _SHADPS4_USER_CFGDIR, SHADPS4_BIN, SHADPS4_DLCS, SHADPS4_ROMS, SHADPS4_SAVES, SHADPS4_TOML

from ... import Command
from retrobox.paths import configure_emulator, mkdir_if_not_exists
from ...controller import generate_sdl_game_controller_config
from ...utils import vulkan
from ..Generator import Generator

if TYPE_CHECKING:
    from retrobox.configgen.typedefs import HotkeysContext

_logger = logging.getLogger(__name__)

class shadPS4Generator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "shadps4",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]}
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        mkdir_if_not_exists(_SHADPS4_USER_CFGDIR)
        mkdir_if_not_exists(SHADPS4_SAVES)
        mkdir_if_not_exists(SHADPS4_ROMS)
        mkdir_if_not_exists(SHADPS4_DLCS)

        # Check Vulkan first before doing anything
        discrete_index = -1
        if vulkan.is_available():
            _logger.debug("Vulkan driver is available on the system.")
            vulkan_version = vulkan.get_version()
            if vulkan_version > "1.3":
                _logger.debug("Using Vulkan version: %s", vulkan_version)
                if vulkan.has_discrete_gpu():
                    _logger.debug(
                        "A discrete GPU is available on the system. " + 
                        "We will use that for performance")
                    discrete_index = vulkan.get_discrete_gpu_index()
                    if discrete_index:
                        _logger.debug("Using Discrete GPU Index: %s for shadPS4", discrete_index)
                    else:
                        _logger.debug("Couldn't get discrete GPU index")
                        discrete_index = 0
                else:
                    _logger.debug("Discrete GPU is not available on the system. Using default.")
            else:
                _logger.debug("Vulkan version: %s is not compatible with shadPS4", vulkan_version)
        else:
            _logger.debug("*** Vulkan driver required is not available on the system!!! ***")
            sys.exit(1)

        # Adjust the config.toml file
        config: dict[str, dict[str, object]] | tomlkit.TOMLDocument = {}
        
        # Check if the file exists
        if SHADPS4_TOML.is_file():
            try:
                with SHADPS4_TOML.open("r") as f:
                    config = tomlkit.load(f)
            except Exception as e:
                 _logger.error("Failed to load existing shadps4 config: %s. Will create default.", e)

        # If config is empty, create default structure
        if not config:
             _logger.info("Creating default shadps4 config at %s", SHADPS4_TOML)
             config = {
                "General": {
                    "isPS4Pro": False,
                    "isTrophyPopupDisabled": False,
                    "trophyNotificationDuration": 6.0,
                    "playBGM": False,
                    "BGMvolume": 50,
                    "enableDiscordRPC": system.config.get_bool('discordrpc', False, return_values=(True, False)),
                    "logFilter": "",
                    "logType": "async",
                    "userName": getpass.getuser(),
                    "updateChannel": "Release",
                    "chooseHomeTab": "General",
                    "showSplash": False,
                    "autoUpdate": False,
                    "alwaysShowChangelog": False,
                    "sideTrophy": "right",
                    "separateUpdateEnabled": False,
                    "compatibilityEnabled": False,
                    "checkCompatibilityOnStartup": False,
                },
                "Input": {
                    "cursorState": 1,
                    "cursorHideTimeout": 5,
                    "backButtonBehavior": "left",
                    "useSpecialPad": False,
                    "specialPadClass": 1,
                    "isMotionControlsEnabled": True,
                    "useUnifiedInputConfig": True,
                },
                "GPU": {
                    "screenWidth": int(gameResolution["width"]),
                    "screenHeight": int(gameResolution["height"]),
                    "nullGpu": False,
                    "copyGPUBuffers": False,
                    "dumpShaders": False,
                    "patchShaders": True,
                    "vblankDivider": 1,
                    "Fullscreen": True,
                    "FullscreenMode": "Fullscreen (Borderless)",
                    "allowHDR": False,
                },
                "Vulkan": {
                    "gpuId": int(discrete_index),
                    "validation": False,
                    "validation_sync": False,
                    "validation_gpu": False,
                    "crashDiagnostic": False,
                    "hostMarkers": False,
                    "guestMarkers": False,
                    "rdocEnable": False,
                },
                "Debug": {
                    "DebugDump": False,
                    "CollectShader": False,
                    "isSeparateLogFilesEnabled": False,
                    "FPSColor": True,
                },
                "Keys": {
                    "TrophyKey": ""
                 },
                "GUI": {
                    "installDirs": [str(SHADPS4_ROMS)],
                    "saveDataPath": str(SHADPS4_SAVES),
                    "loadGameSizeEnabled": True,
                    "addonInstallDir": str(SHADPS4_DLCS),
                    "emulatorLanguage": "en_US",
                    "backgroundImageOpacity": 50,
                    "showBackgroundImage": True,
                    "mw_width": int(gameResolution["width"]),
                    "mw_height": int(gameResolution["height"]),
                    "theme": 0,
                    "iconSize": 36,
                    "sliderPos": 0,
                    "iconSizeGrid": 69,
                    "sliderPosGrid": 0,
                    "gameTableMode": 0,
                    "geometry_x": 0,
                    "geometry_y": 0,
                    "geometry_w": int(gameResolution["width"]),
                    "geometry_h": int(gameResolution["height"]),
                    "pkgDirs": [str(SHADPS4_ROMS)],
                    "elfDirs": [],
                    "recentFiles": [],
                },
                "Settings": {
                    "consoleLanguage": 1
                },
             }

        # --- Apply Batocera Specific Overrides ---
        # General
        config.setdefault("General", {})["autoUpdate"] = False
        config.setdefault("General", {})["enableDiscordRPC"] = False
        config.setdefault("General", {})["userName"] = "Batocera"

        # GPU
        gpu_config = config.setdefault("GPU", {})
        gpu_config["Fullscreen"] = True
        gpu_config["FullscreenMode"] = "Fullscreen (Borderless)"
        gpu_config["screenWidth"] = int(gameResolution["width"])
        gpu_config["screenHeight"] = int(gameResolution["height"])

        # GUI
        gui_config = config.setdefault("GUI", {})
        gui_config["addonInstallDir"] = str(SHADPS4_DLCS)
        gui_config["installDirs"] = [str(SHADPS4_ROMS)]
        gui_config["saveDataPath"] = str(SHADPS4_SAVES)
        gui_config["mw_width"] = int(gameResolution["width"])
        gui_config["mw_height"] = int(gameResolution["height"])
        gui_config["geometry_w"] = int(gameResolution["width"])
        gui_config["geometry_h"] = int(gameResolution["height"])
        gui_config["pkgDirs"] = [str(SHADPS4_ROMS)]

        # Vulkan - Set the detected GPU ID
        config.setdefault("Vulkan", {})["gpuId"] = int(discrete_index)

        # Options
        if system.config.get_bool("shadps4_hdr"):
            gpu_config["allowHDR"] = True
        else:
            gpu_config["allowHDR"] = False

        settings_config = config.setdefault("Settings", {})
        if system.config.get("shadps4_console_lang"):
            settings_config["consoleLanguage"] = int(system.config["shadps4_console_lang"])
        else:
            settings_config["consoleLanguage"] = 1

        # Create necessary directories if they do not exist
        mkdir_if_not_exists(SHADPS4_TOML.parent)

        # Now write the updated toml
        with SHADPS4_TOML.open("w") as f:
            tomlkit.dump(config, f)

        # Change to the configPath directory before running
        os.chdir(_SHADPS4_CFGDIR)

        # Run command
        if configure_emulator(rom):
            command_array: list[str | Path] = [SHADPS4_BIN]
        else:
            command_array: list[str | Path] = [SHADPS4_BIN, rom.parent / "eboot.bin"]

        return Command.Command(
            array=command_array,
            env={
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
                "SDL_JOYSTICK_HIDAPI": "0"
            }
        )

    def getInGameRatio(self, config, gameResolution, rom):
        return 16 / 9
