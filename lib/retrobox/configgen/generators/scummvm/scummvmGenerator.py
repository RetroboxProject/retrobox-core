from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from retrobox.configgen import Command
from retrobox.configgen.controller import Controller, generate_sdl_game_controller_config
from retrobox.configgen.generators.Generator import Generator
from retrobox.configgen.generators.scummvm.scummvm_paths import _SCUMMVM_EXTRA, _SCUMMVM_SAVES, _SCUMMVM_XDG, SCUMMVM_CFG
from retrobox.paths import CACHE, LOGS, SCREENSHOTS, ensure_parents_and_open, mkdir_if_not_exists
from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser

if TYPE_CHECKING:
    from retrobox.configgen.typedefs import HotkeysContext


class ScummVMGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "scummvm",
            "keys": { "exit": ["KEY_LEFTALT", "KEY_F4"], "menu": ["KEY_LEFTCTRL", "KEY_F5"] }
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        # create <bios dir>/scummvm/extra folder if it doesn't exist
        mkdir_if_not_exists(_SCUMMVM_EXTRA)

        # create / modify scummvm config file as needed
        scummConfig = CaseSensitiveConfigParser()
        if SCUMMVM_CFG.exists():
            scummConfig.read(SCUMMVM_CFG)

        if not scummConfig.has_section("scummvm"):
            scummConfig.add_section("scummvm")
        # set gui_browser_native to false
        scummConfig.set("scummvm", "gui_browser_native", "false")

        # save the ini file
        with ensure_parents_and_open(SCUMMVM_CFG, 'w') as configfile:
            scummConfig.write(configfile)

        # Find rom path
        # 1. If a .scummvm file exists and contains a valid <game id>, use the <game id>
        # 2. If an empty <game id>.scummvm file exists, use the <game id>
        # 3. Otherwise, auto detect the game

        if rom.is_dir():
            # squashfs: find a <game name>.scummvm file
            rom_file = next(rom.glob("*.scummvm"), None)
            rom_path = rom
        else:
            # .scummvm: use rom as file
            rom_file = rom
            rom_path = rom.parent

        target = "--auto-detect"

        if rom_file is not None:
            game_id = rom_file.read_text().strip().lower() or rom_file.stem

            if re.match(r'^(?:[a-z0-9-]+:)?[a-z0-9-]+$', game_id) is not None:
                target = game_id

        # pad number
        id = 0
        if pad := Controller.find_player_number(playersControllers, 1):
            id = pad.index

        commandArray = ["/usr/bin/scummvm", "-f"]

        # set the resolution
        commandArray.append(f"--window-size={gameResolution['width']},{gameResolution['height']}")

        ## user options

        # scale factor
        commandArray.append(f"--scale-factor={system.config.get('scumm_scale', '3')}")

        # sclaer mode
        commandArray.append(f"--scaler={system.config.get('scumm_scaler_mode', 'normal')}")

        #  stretch mode
        if stretch := system.config.get("scumm_stretch"):
            commandArray.append(f"--stretch-mode={stretch}")

        # renderer
        commandArray.append(f"--renderer={system.config.get('scumm_renderer', 'opengl')}")

        # language
        if language := system.config.get("scumm_language"):
            commandArray.extend(["-q", f"{language}"])

        # logging
        commandArray.append(f"--logfile={LOGS}/scummvm.log")

        commandArray.extend(
            [f"--joystick={id}",
            f"--screenshotspath={SCREENSHOTS}",
            f"--extrapath={_SCUMMVM_EXTRA}",
            f"--savepath={_SCUMMVM_SAVES}",
            f"--path={rom_path}",
            f"{target}"]
        )

        # Determine SDL Video Driver
        sdl_videodriver = "wayland" if "WAYLAND_DISPLAY" in os.environ else "x11"

        return Command.Command(
            array=commandArray,
            env={
                "SDL_VIDEODRIVER": sdl_videodriver,
                "XDG_CONFIG_HOME": _SCUMMVM_XDG,
                "XDG_CACHE_HOME": CACHE,
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers)
            }
        )

    def getInGameRatio(self, config, gameResolution, rom):
        if config.get("scumm_stretch") in ["fit_force_aspect", "pixel-perfect"]:
            return 4/3
        return 16/9
