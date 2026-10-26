from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Final

import tomlkit

from retrobox.configgen import Command
from retrobox.configgen.controller import Controller
from retrobox.configgen.generators.Generator import Generator
from retrobox.configgen.generators.melonds.melonds_paths import _MELONDS_CHEATS, _MELONDS_CFGDIR, _MELONDS_ROMS, _MELONDS_SAVES, _MELONDS_XDG, DSI_ARM7_BIOS, DSI_ARM9_BIOS, DSI_FIRMWARE, DSI_NAND, MELONDS_CFG, NDS_ARM7_BIOS, NDS_ARM9_BIOS, NDS_FIRMWARE
from retrobox.paths import BIOS, mkdir_if_not_exists

if TYPE_CHECKING:
    from retrobox.configgen.typedefs import HotkeysContext

class MelonDSGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "melonds",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]}
        }

    @abstractmethod
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        # Verify paths
        mkdir_if_not_exists(_MELONDS_SAVES)
        mkdir_if_not_exists(_MELONDS_CHEATS)
        mkdir_if_not_exists(_MELONDS_CFGDIR)

        # Load existing config if file exists
        if MELONDS_CFG.exists():
            with MELONDS_CFG.open() as toml_file:
                config = tomlkit.load(toml_file)
        else:
            config = {}

        # Define base configuration
        base_config: dict[str, Any] = {
            "MouseHide": False,
            "LastBIOSFolder": str(BIOS),
            "PauseLostFocus": False,
            "LastROMFolder": str(_MELONDS_ROMS),
            "MouseHideSeconds": 5,
            "DS": {
                "FirmwarePath": str(NDS_FIRMWARE),
                "BIOS7Path": str(NDS_ARM7_BIOS),
                "BIOS9Path": str(NDS_ARM9_BIOS)
            },
            "DLDI": {
                "FolderPath": str(_MELONDS_SAVES),
                "ImagePath": "dldi.bin",
                "Enable": True
            },
            "DSi": {
                "FullBIOSBoot": False,
                "FirmwarePath": str(DSI_FIRMWARE),
                "BIOS9Path": str(DSI_ARM9_BIOS),
                "BIOS7Path": str(DSI_ARM7_BIOS),
                "NANDPath": str(DSI_NAND),
                "SD": {
                    "FolderPath": str(_MELONDS_SAVES),
                    "ImagePath": "dsisd.bin",
                    "Enable": True
                }
            },
            "Emu": {
                "DirectBoot": True,
                "ExternalBIOSEnable": True
            },
            "Instance0": {
                "SaveFilePath": str(_MELONDS_SAVES),
                "SavestatePath": str(_MELONDS_SAVES),
                "CheatFilePath": str(_MELONDS_CHEATS),
                "EnableCheats": False,
                "Joystick": {},
                "Firmware": {
                    "MAC": "",
                    "BirthdayDay": 1,
                    "BirthdayMonth": 1,
                    "Language": 1,
                    "Message": "",
                    "OverrideSettings": True
                },
                "Window0": {
                    "ScreenRotation": 0,
                    "ScreenSwap": False,
                    "ScreenLayout": 0,
                    "ScreenSizing": 0,
                    "IntegerScaling": False,
                    "ShowOSD": False
                },
                "Window1": {
                    "Enabled": False,
                    "ScreenRotation": 0,
                    "ScreenSwap": False,
                    "ScreenLayout": 0,
                    "ScreenSizing": 5,
                    "IntegerScaling": False
                }
            },
            "3D": {
                "Renderer": 1,
                "GL": {
                    "ScaleFactor": 5,
                    "BetterPolygons": False
                }
            },
            "Screen": {
                "VSync": False,
                "UseGL": False
            }
        }

        ## User selected options

        # Override Renderer and UseGL
        if "melonds_renderer" in system.config:
            renderer = system.config.get_int("melonds_renderer")
            base_config["3D"]["Renderer"] = renderer
            base_config["Screen"]["UseGL"] = (renderer != 0)

        if vsync := system.config.get_bool("melonds_vsync"):
            base_config["Screen"]["VSync"] = vsync
            base_config["Screen"]["VSyncInterval"] = 1

        # Cheater! Enable cheats if the option is set
        base_config["Instance0"]["EnableCheats"] = system.config.get_bool("melonds_cheats", False)

        # Framerate
        base_config["LimitFPS"] = system.config.get_bool("melonds_framerate", True)

        # Resolution
        if (resolution := system.config.get_int("melonds_resolution")) is not system.config.MISSING:
            base_config["3D"]["GL"]["ScaleFactor"] = resolution
            base_config["3D"]["GL"]["HiresCoordinates"] = (resolution == 2)

        # Polygons
        if polygons := system.config.get_bool("melonds_polygons"):
            base_config["3D"]["GL"]["BetterPolygons"] = polygons

        # OSD
        base_config["Instance0"]["Window0"]["ShowOSD"] = system.config.get_bool("melonds_osd", False)

        # Console
        base_config["Emu"]["ConsoleType"] = system.config.get_int("melonds_console", 0)
        
        # Override Firmware settings
        base_config["Instance0"]["Firmware"]["OverrideSettings"] = system.config.get_bool("melonds_use_fw_settings", False)

        # Firmware Language
        base_config["Instance0"]["Firmware"]["Language"] = system.config.get_int("melonds_language", 1)

        # Birthday date
        base_config["Instance0"]["Firmware"]["BirthdayDay"] = system.config.get_int("melonds_day", 1)
        base_config["Instance0"]["Firmware"]["BirthdayMonth"] = system.config.get_int("melonds_month", 1)

        # Scaling (Matches TOML boolean type)
        scaling = system.config.get_bool("melonds_scaling", False)

        # Check if dual screen mode is enabled
        is_dual_screen_enabled = system.config.get_bool("melonds_dual_screen", False)

        if is_dual_screen_enabled:
            # Window0 (Top Screen)
            base_config["Instance0"]["Window0"]["ScreenRotation"] = 0
            base_config["Instance0"]["Window0"]["ScreenSwap"] = False
            base_config["Instance0"]["Window0"]["ScreenLayout"] = 0
            base_config["Instance0"]["Window0"]["ScreenSizing"] = 4
            base_config["Instance0"]["Window0"]["IntegerScaling"] = scaling

            # Window1 (Bottom Screen)
            base_config["Instance0"]["Window1"]["Enabled"] = True
            base_config["Instance0"]["Window1"]["ScreenRotation"] = 0
            base_config["Instance0"]["Window1"]["ScreenSwap"] = False
            base_config["Instance0"]["Window1"]["ScreenLayout"] = 0
            base_config["Instance0"]["Window1"]["ScreenSizing"] = 5
            base_config["Instance0"]["Window1"]["IntegerScaling"] = scaling
        else:
            base_config["Instance0"]["Window1"]["Enabled"] = False
            base_config["Instance0"]["Window0"]["ScreenRotation"] = system.config.get_int("melonds_rotation", 0)
            base_config["Instance0"]["Window0"]["ScreenSwap"] = system.config.get_bool("melonds_screenswap", False)
            base_config["Instance0"]["Window0"]["ScreenLayout"] = system.config.get_int("melonds_layout", 0)
            base_config["Instance0"]["Window0"]["ScreenSizing"] = system.config.get_int("melonds_screensizing", 0)
            base_config["Instance0"]["Window0"]["IntegerScaling"] = scaling

        # Map controllers
        melonDSMapping = {
            "a":        "A",
            "b":        "B",
            "select":   "Select",
            "start":    "Start",
            "right":    "Right",
            "left":     "Left",
            "up":       "Up",
            "down":     "Down",
            "pagedown": "R",
            "pageup":   "L",
            "x":        "X",
            "y":        "Y"
        }

        val = -1
        # Only use Player 1 controls
        if pad := Controller.find_player_number(playersControllers, 1):
            for index in pad.inputs:
                input = pad.inputs[index]
                if input.name not in melonDSMapping:
                    continue
                option = melonDSMapping[input.name]
                # Workaround - SDL numbers?
                val = input.id
                if val == "0":
                    if option == "Up":
                        val = 257
                    elif option == "Down":
                        val = 260
                    elif option == "Left":
                        val = 264
                    elif option == "Right":
                        val = 258
                base_config["Instance0"]["Joystick"][option] = int(val)

        # Update base_config with any existing values
        config.update(base_config)

        # Write updated configuration back to the file
        with MELONDS_CFG.open("w") as toml_file:
            tomlkit.dump(config, toml_file)

        commandArray = ["/usr/bin/melonDS", "-f", rom]
        return Command.Command(
            array=commandArray,
            env={
                "XDG_CONFIG_HOME": _MELONDS_XDG,
                "XDG_DATA_HOME": _MELONDS_SAVES
            }
        )
