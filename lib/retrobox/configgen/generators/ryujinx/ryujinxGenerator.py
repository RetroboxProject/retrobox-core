from __future__ import annotations

import logging
import shutil
import subprocess
import stat
import hashlib
from shutil import copyfile
from pathlib import Path
from typing import TYPE_CHECKING
from retrobox.configgen.generators.ryujinx.ryujinx_config import writeRyujinxConfig
from retrobox.paths import (
    DEFAULTS_DIR,
    SAVES,
    configure_emulator,
    ensure_symlink,
    mkdir_if_not_exists
)

from ...controller import generate_sdl_game_controller_config

from ... import Command

from ..Generator import Generator
from ..eden.edenPaths import SWITCH_FIRMWARE, SWITCH_KEYS, SWITCH_MODS_DIR, SWITCH_ROMS
from .ryujinxPaths import (
    _RYUJINX_XDG,
    RYUJINX_BIN,
    RYUJINX_BIS,
    RYUJINX_CONFIG,
    RYUJINX_CONFIG_FILE,
    RYUJINX_CONFIG_FILE_BFR,
    RYUJINX_CONFIG_FILE_TPL,
    RYUJINX_MODS_LINK,
    RYUJINX_SAVE_BASE,
    RYUJINX_SYSTEM_CONFIG_DIR,
    RYUJINX_SYSTEM_DIR,
    RYUJINX_USER_DIR,
    RYUJINX_SYSTEM_SAVES,
    RYUJINX_USER_SAVES
)
from ...input import Input

_logger = logging.getLogger(__name__)



if TYPE_CHECKING:
    from retrobox.configgen.typedefs import HotkeysContext

# copiar todo lo de una carpeta a otra (sincronizar .keys)
def sync_keys(src_dir: Path, dst_dir: Path):
    if not src_dir.is_dir():
        return

    dst_dir.mkdir(parents=True, exist_ok=True)

    for f in src_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, dst_dir / f.name)

# calcular el checksum de todo un directorio - para ver integridad de firmware
def compute_dir_checksum(path: Path) -> str:
    files = sorted(p for p in path.rglob("*") if p.is_file())
    h = hashlib.sha256()

    for f in files:
        h.update(f.read_bytes())

    return h.hexdigest()

# sincronizar firmware de la carpeta bios con lo que necesita ryujinx (carpetas con 00)
def sync_firmware(src: Path, registered: Path, checksum_file: Path):
    if not src.is_dir():
        return

    new_checksum = compute_dir_checksum(src)

    old_checksum = None
    if checksum_file.exists():
        old_checksum = checksum_file.read_text().strip()

    if new_checksum == old_checksum:
        return  # nada que hacer

    # rebuild
    if registered.exists():
        shutil.rmtree(registered)

    registered.mkdir(parents=True, exist_ok=True)

    for f in src.glob("*.nca"):
        dst_dir = registered / f.name
        dst_dir.mkdir()
        shutil.copy2(f, dst_dir / "00")

    checksum_file.parent.mkdir(parents=True, exist_ok=True)
    checksum_file.write_text(new_checksum)

def getCurrentCard() -> str | None:
    proc = subprocess.Popen([f"{DEFAULTS_DIR}/data/switch/detectvideo.sh"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    for val in out.decode().splitlines():
        return val # return the first line


class RyujinxGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "ryujinx-emu",
            "keys": { "menu": "KEY_F4"}
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        _logger.warning("DEBUG: generate() llamado, emulator=%s", system.config['emulator'])
        script = DEFAULTS_DIR / "data/switch/detectvideo.sh"
        st = script.stat()
        script.chmod(st.st_mode | stat.S_IEXEC)

        mkdir_if_not_exists(RYUJINX_CONFIG)

        copyfile(RYUJINX_CONFIG_FILE_TPL, RYUJINX_CONFIG_FILE)

        # Crear estructura base
        mkdir_if_not_exists(RYUJINX_BIS)
        mkdir_if_not_exists(RYUJINX_BIS / "system/Contents")

        # Firmware + keys
        sync_keys(SWITCH_KEYS, RYUJINX_SYSTEM_CONFIG_DIR)

        sync_firmware(
            SWITCH_FIRMWARE,
            RYUJINX_SYSTEM_DIR / "Contents/registered",
            RYUJINX_CONFIG / "checksum_firmware.txt"
        )
        
        # Saves base
        mkdir_if_not_exists(RYUJINX_SAVE_BASE)

        # USER SAVE
        mkdir_if_not_exists(RYUJINX_USER_SAVES)
        ensure_symlink(RYUJINX_USER_SAVES, RYUJINX_USER_DIR)

        # SYSTEM SAVE
        mkdir_if_not_exists(RYUJINX_SYSTEM_SAVES)
        ensure_symlink(RYUJINX_SYSTEM_SAVES, RYUJINX_SYSTEM_DIR / "save")

        # MODS
        mkdir_if_not_exists(SWITCH_MODS_DIR)
        ensure_symlink(SWITCH_MODS_DIR, RYUJINX_MODS_LINK)

        _logger.debug("Controller mapping before: {}".format(generate_sdl_game_controller_config(playersControllers)))

        #Configuration update
        sdl_mapping = writeRyujinxConfig(f"{RYUJINX_CONFIG_FILE}", f"{RYUJINX_CONFIG_FILE_BFR}", f"{RYUJINX_CONFIG_FILE_TPL}", system, playersControllers)

        _logger.debug("Controller mapping after: {}".format(str(sdl_mapping)))

        environment = { 
                        "SDL_JOYSTICK_HIDAPI": "1",
                        "SDL_JOYSTICK_HIDAPI_XBOX": "1",
                        "SDL_JOYSTICK_HIDAPI_STEAMDECK" : "1",
                        "SDL_JOYSTICK_HIDAPI_PS4" : "1",
                        "SDL_JOYSTICK_HIDAPI_PS5" : "1",
                        "SDL_JOYSTICK_HIDAPI_SWITCH" : "1",
                        "SDL_GAMECONTROLLERCONFIG": sdl_mapping,
                        "DOTNET_EnableAlternateStackCheck":"1",
                        "XDG_CONFIG_HOME":f"{_RYUJINX_XDG}",
                        "XDG_DATA_HOME":f"{SAVES}",
        }

        commandArray = []
        commandArray.extend([f"{RYUJINX_BIN}"])
        if not configure_emulator(rom):
            commandArray.extend([rom])

        return Command.Command(array=commandArray, env=environment)
    
    

