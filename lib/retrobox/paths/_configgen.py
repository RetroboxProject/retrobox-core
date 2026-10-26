"""retrobox.paths constants consumed by configgen and emulatorlauncher.py.

Covers emulator content directories (bios, saves, screenshots...), the
ephemeral state of an in-progress game session (RUNTIME_DIR and its
subdirectories), and system scripts/utilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from ._base import DATA_DIR, LIBEXEC_DIR, SHARE_DIR, RUNTIME_DIR, check_env_dirs, get_configured_path

EMU_FEATURES_DIR: Final = SHARE_DIR / "emu_features"
SYSTEMS_CONF_DIR: Final = SHARE_DIR / "systems_config"

# Directories for emulator content
#
# SAVES and BIOS are two of the three ini-managed [paths] keys (alongside
# ROMS in _base.py): always read from retrobox.ini via get_configured_path,
# never from os.environ. os.environ is only ever populated from [environ]
# -- it plays no part in resolving these.
SAVES: Final = get_configured_path("saves_dir", DATA_DIR / "saves")
SCREENSHOTS: Final = check_env_dirs("SCREENSHOTS_DIR", DATA_DIR / "screenshots")
RECORDINGS: Final = check_env_dirs("RECORDINGS_DIR", DATA_DIR / "recordings")
BIOS: Final = get_configured_path("bios_dir", DATA_DIR / "bios")
OVERLAYS: Final = check_env_dirs("OVERLAYS_DIR", DATA_DIR / "overlay")
CHEATS: Final = check_env_dirs("CHEATS_DIR", DATA_DIR / "cheats")

_SHADERS_DIR: Final = check_env_dirs("SHADERS_DIR", DATA_DIR / "shaders")
_SHADERS_DEF_DIR: Final = check_env_dirs("SHADERS_DEFAULT_DIR", SHARE_DIR / "shaders")

_DECORATIONS_DIR: Final = check_env_dirs("BEZELS_DIR", DATA_DIR / "decorations")
# Default (RetroBat) bezels are not shipped: tools/decorations/retrobat-bezels.sh
# downloads them here.
_DECORATIONS_DEF_DIR: Final = check_env_dirs("BEZELS_DEFAULT_DIR", DATA_DIR / "decorations-default")

_SYSTEM_SCRIPTS: Final = SHARE_DIR / "scripts"

# Internal executables (not meant to be run by hand): libexec/stubs/ are the
# helper commands configgen calls (resolution, keyboard layout...).
NVIDIA_POWERD_SCRIPT: Final = LIBEXEC_DIR / "nvidia-powerd-service"

# ---------------------------------------------------------------------------
# MangoHud (retrobox's own build, with bezel support)
#
# Installed under its own private prefix instead of /usr/local so it never
# shadows (or gets shadowed by) whatever MangoHud the user may already have
# installed system-wide. emulatorlauncher.py prefers this build when it's
# present and only falls back to a system-wide "mangohud" (found via PATH)
# otherwise. It is provided by the retrobox-mangohud package (or its
# install.sh), which installs into this prefix.
# ---------------------------------------------------------------------------
MANGOHUD_PREFIX_DIR: Final = LIBEXEC_DIR / "mangohud"
MANGOHUD_BIN: Final = MANGOHUD_PREFIX_DIR / "bin" / "mangohud"
MANGOHUD_VULKAN_LAYER_DIR: Final = MANGOHUD_PREFIX_DIR / "share" / "vulkan" / "implicit_layer.d"

# Runtime dir (ephemeral state of an in-progress game session): see _base.py

SQUASHFS_DIR: Final = RUNTIME_DIR / "squashfs"
ROTATION_FILE: Final = RUNTIME_DIR / "rk-rotation"
OVERLAY_BASE_DIR: Final = RUNTIME_DIR / "overlays"
MAME_SOFTWARE_DIR: Final = RUNTIME_DIR / "mame_software"
MAME_ARTWORK_DIR: Final = RUNTIME_DIR / "mame_artwork"
CMDFILES_DIR: Final = RUNTIME_DIR / "cmdfiles"
SHADER_BEZELS_DIR: Final = RUNTIME_DIR / "shader_bezels"
HUD_CONFIG_FILE: Final = RUNTIME_DIR / "hud.config"
GUN_OVERLAYS_DIR: Final = RUNTIME_DIR / "batocera-overlays"


def configure_emulator(rom: Path, /) -> bool:
    """Return True when `rom` denotes a "configure the emulator" pseudo-rom.

    Args:
        rom: The rom path (or pseudo-path) requested by the frontend.

    Returns:
        True if this is the special "config" rom or a ".menu" entry.
    """
    return str(rom) == "config" or rom.suffix == ".menu"