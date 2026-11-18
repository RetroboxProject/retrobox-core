# edenPaths.py
import os
from pathlib import Path
from typing import Final
from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import BIOS, EMULATORS_CONFIG, ROMS, SAVES, ensure_symlink, mkdir_if_not_exists

# --- Base ---
SWITCH_BIOS: Final = BIOS / "switch"
SWITCH_KEYS: Final = SWITCH_BIOS / "keys"
SWITCH_FIRMWARE: Final = SWITCH_BIOS / "firmware"

EDEN: Final = EmulatorBinary("eden-emu", ("eden", "eden-emu"), installer="eden")
_EDEN_XDG: Final = EMULATORS_CONFIG / 'eden-emu'
_EDEN_CONFIG: Final = _EDEN_XDG / "eden"
_EDEN_INI: Final = _EDEN_CONFIG / "qt-config.ini"
EDEN_DATA: Final = SAVES / "switch" / "eden"
EDEN_KEYS: Final = EDEN_DATA / "keys"
EDEN_REGISTERED: Final = EDEN_DATA / "nand/system/Contents/registered"

SWITCH_UPDATE_DIR: Final = ROMS / "switch_update"
SWITCH_DLC_DIR: Final = SWITCH_UPDATE_DIR / "dlc"
SWITCH_UPDATES_DIR: Final = SWITCH_UPDATE_DIR / "update"
SWITCH_ROMS: Final = ROMS / "switch"
SWITCH_MODS_DIR: Final = SWITCH_UPDATE_DIR / "mods"

# Saves
SAVE_BASE: Final = EDEN_DATA
USER_SAVE_TARGET: Final = SAVE_BASE / "save/save_user"
SYSTEM_SAVE_TARGET: Final = SAVE_BASE / "save/save_system"

EDEN_USER_SAVE_LINK: Final = EDEN_DATA / "nand/user/save"
EDEN_SYSTEM_SAVE_LINK: Final = EDEN_DATA / "nand/system/save"
EDEN_MODS_LINK: Final = EDEN_DATA / "load"

# GAMEPAD RARE CONFIG
# Controllers that expose the D-pad as BTN_DPAD_* while SDL turns it into a hat
EDEN_RARE_DPAD_GUIDS = {
    "030000007e0500000920000000006803",  # Switch Pro Controller
}

def setup_eden_environments():
    """Create every folder and symlink Eden needs."""
    # 1. Create the folders
    dirs_to_create = [
        SWITCH_BIOS, SWITCH_KEYS, SWITCH_FIRMWARE,
        EDEN_DATA, os.path.join(EDEN_DATA, "nand/system/Contents"),
        SWITCH_UPDATE_DIR, SWITCH_DLC_DIR, SWITCH_UPDATES_DIR, SWITCH_ROMS,
        USER_SAVE_TARGET, SYSTEM_SAVE_TARGET, SWITCH_MODS_DIR
    ]
    
    for d in dirs_to_create:
        mkdir_if_not_exists(Path(d))

    # 2. Create the symlinks
    ensure_symlink(SWITCH_KEYS, EDEN_KEYS)
    ensure_symlink(SWITCH_FIRMWARE, EDEN_REGISTERED)
    ensure_symlink(USER_SAVE_TARGET, EDEN_USER_SAVE_LINK)
    ensure_symlink(SYSTEM_SAVE_TARGET, EDEN_SYSTEM_SAVE_LINK)
    ensure_symlink(SWITCH_MODS_DIR, EDEN_MODS_LINK)