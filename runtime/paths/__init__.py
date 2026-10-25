"""runtime.paths — Retrobox's single entry point for paths and constants.

Internally split by subsystem:
    _base.py       -> generic (XDG, ROOTDIR, retrobox.ini bootstrap, FS helpers)
    _configgen.py  -> configgen / emulatorlauncher / launcher
    _frontend.py   -> EmulationStation (runtime/startup/frontend_conf)
    _gamepadly.py  -> the 4 constants emulatorlauncher.py needs to
                      instantiate GamepadManager (gamepadly itself no
                      longer imports anything from here directly)

Nothing changes from the outside, though: everything is still imported
the same way as before, `from runtime.paths import X`. None of the
~100 files that already do that import need to be touched.

If you add a new constant, first decide which subsystem it belongs to
and define it in the corresponding _file.py (or create a new one for a
different subsystem) — then add it here. Don't define it directly in
this __init__.py.
"""

from __future__ import annotations
import logging
import os
from pathlib import Path

from ._base import (
    CACHE,
    CONF_INIT,
    CONFIG_DIR,
    DATA_DIR,
    DATAINIT_DIR,
    DEFAULTS_DIR,
    EMULATORS,
    EMULATORS_CONFIG,
    ENV_FILE,
    HOME_INIT,
    HOOKS,
    IGNORED_SYSTEMS,
    LOGS,
    RESOURCES_DIR,
    RETROBOX_INI,
    RUNTIME_DIR,
    RETROBOX_ROOTDIR,
    ROMS,
    STATE_DIR,
    SYSCONF_DIR,
    CONFIG_LAYERS,
    _SYSTEM_LOCAL_BIN,
    _SYSTEM_LOCAL_SHARE,
    _USER_HOME,
    _XDG_CACHE,
    _XDG_CONFIG,
    _XDG_DATA,
    _XDG_STATE,
    check_env_dirs,
    ensure_parents_and_open,
    ensure_symlink,
    get_ini_value,
    layered_dirs,
    layered_file,
    layered_files,
    mkdir_if_not_exists,
)
from ._configgen import (
    BIOS,
    CHEATS,
    CMDFILES_DIR,
    GUN_OVERLAYS_DIR,
    HUD_CONFIG_FILE,
    MAME_ARTWORK_DIR,
    MAME_SOFTWARE_DIR,
    OVERLAY_BASE_DIR,
    OVERLAYS,
    RECORDINGS,
    ROTATION_FILE,
    RUNTIME_DIR,
    SAVES,
    SCREENSHOTS,
    SHADER_BEZELS_DIR,
    SQUASHFS_DIR,
    _DECORATIONS_DEF_DIR,
    _DECORATIONS_DIR,
    EMU_FEATURES_DIR,
    MANGOHUD_BIN,
    MANGOHUD_PREFIX_DIR,
    MANGOHUD_VULKAN_LAYER_DIR,
    NVIDIA_POWERD_SCRIPT,
    _SHADERS_DEF_DIR,
    _SHADERS_DIR,
    _SYSTEM_SCRIPTS,
    SYSTEMS_CONF_DIR,
    UTILS_DIR,
    configure_emulator,
)
from ._frontend import (
    ES_EXECUTABLE,
    ES_FEATURES_CFG,
    ES_FEATURES_TMP,
    ES_GAMES_METADATA,
    ES_GUNS_ART_METADATA,
    ES_GUNS_METADATA,
    ES_INI_CFG,
    ES_INI_TMP,
    ES_INPUT_CFG,
    ES_SETTINGS_CFG,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    ES_WHEELS_METADATA,
    _ES_RESOURCES_DIR,
    FRONTEND_DIR,
    FRONTEND_HOME,
    MUSIC_DIR,
    THEMES_DIR,
    _USER_ES_DIR,
)
from ._gamepadly import (
    GAMEPADLY_MAPPER,
    _GAMEPADLY_DIR,
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
)
from ._env import exported_environment

# Child processes (emulatorlauncher, shell hooks...) inherit the very same
# directories this process resolved.
os.environ.update({name: str(path) for name, path in exported_environment().items()})

# The "real" public API (without the underscore-prefixed names, which
# stay importable for compatibility but shouldn't be used in new code
# outside of the existing configgen/frontend_conf).
__all__ = [
    # _base
    "CACHE",
    "CONF_INIT",
    "CONFIG_DIR",
    "DATA_DIR",
    "DATAINIT_DIR",
    "DEFAULTS_DIR",
    "EMULATORS",
    "EMULATORS_CONFIG",
    "ENV_FILE",
    "SYSCONF_DIR",
    "CONFIG_LAYERS",
    "get_ini_value",
    "layered_dirs",
    "layered_file",
    "layered_files",
    "RETROBOX_INI",
    "HOME_INIT",
    "HOOKS",
    "IGNORED_SYSTEMS",
    "LOGS",
    "RESOURCES_DIR",
    "RETROBOX_ROOTDIR",
    "ROMS",
    "STATE_DIR",
    "check_env_dirs",
    "ensure_parents_and_open",
    "ensure_symlink",
    "mkdir_if_not_exists",
    # _configgen
    "BIOS",
    "CHEATS",
    "CMDFILES_DIR",
    "GUN_OVERLAYS_DIR",
    "HUD_CONFIG_FILE",
    "MAME_ARTWORK_DIR",
    "MAME_SOFTWARE_DIR",
    "OVERLAY_BASE_DIR",
    "OVERLAYS",
    "RECORDINGS",
    "ROTATION_FILE",
    "RUNTIME_DIR",
    "SAVES",
    "SCREENSHOTS",
    "SHADER_BEZELS_DIR",
    "SQUASHFS_DIR",
    "MANGOHUD_BIN",
    "MANGOHUD_PREFIX_DIR",
    "MANGOHUD_VULKAN_LAYER_DIR",
    "configure_emulator",
    # _frontend
    "ES_EXECUTABLE",
    "ES_FEATURES_CFG",
    "ES_FEATURES_TMP",
    "ES_GAMES_METADATA",
    "ES_GUNS_ART_METADATA",
    "ES_GUNS_METADATA",
    "ES_INI_CFG",
    "ES_INI_TMP",
    "ES_INPUT_CFG",
    "ES_SETTINGS_CFG",
    "ES_SYSTEMS_CFG",
    "ES_SYSTEMS_TMP",
    "ES_WHEELS_METADATA",
    "FRONTEND_DIR",
    "FRONTEND_HOME",
    "MUSIC_DIR",
    "THEMES_DIR",
    # _gamepadly
    "GAMEPADLY_MAPPER",
]

class DirectoryCreationError(OSError):
    """
    Raised when a required directory cannot be created or accessed.

    Wraps the underlying OSError (FileNotFoundError, PermissionError, etc.)
    and carries the path that failed, so callers can build meaningful
    error messages or notifications.
    """

    def __init__(self, path: Path, original: OSError) -> None:
        self.path = path
        self.original = original
        super().__init__(f"{original}: {path}")


def safe_mkdir(directory: Path, *, notify: bool = True) -> Path:
    """
    Create a directory (and its parents) with unified error handling.

    On failure, logs the error, optionally sends a desktop notification,
    and raises DirectoryCreationError so the caller can decide whether
    to abort or continue.

    Args:
        directory: The directory path to create.
        notify: If True, send a desktop notification on failure.

    Returns:
        The same `directory` Path, for chaining convenience.

    Raises:
        DirectoryCreationError: If the directory cannot be created.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Lazy import to avoid a circular dependency at module load time
        # (notifications.py is in runtime/utils, which may not be on the
        # import path yet when _base.py first runs).
        from runtime.utils.notifications import notify_error  # pylint: disable=import-outside-toplevel

        msg = f"Cannot create directory: {directory}"
        detail = f"{type(exc).__name__}: {exc}"

        _logger = logging.getLogger(__name__)
        _logger.error("%s (%s)", msg, detail)

        if notify:
            notify_error(msg, detail)

        raise DirectoryCreationError(directory, exc) from exc

    return directory