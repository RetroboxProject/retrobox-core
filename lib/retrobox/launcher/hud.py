"""MangoHud overlay: HUD text, bezel background and Vulkan layer environment."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from retrobox.paths import (
    HUD_CONFIG_FILE,
    MANGOHUD_BIN,
    MANGOHUD_PREFIX_DIR,
    MANGOHUD_VULKAN_LAYER_DIR,
)

from .hud_bezel import get_hud_bezel
from .session import effective_core

if TYPE_CHECKING:
    from retrobox.configgen.Command import Command
    from retrobox.configgen.Emulator import Emulator

    from .session import GameSession

_logger = logging.getLogger(__name__)

_HUD_POSITIONS = {"NW": "top-left", "NE": "top-right", "SE": "bottom-right"}
_HUD_PERF_LINES = (
    "background_alpha=0.4",
    "legacy_layout=false",
    "custom_text=%GAMENAME%",
    "custom_text=%SYSTEMNAME%",
    "custom_text=%EMULATORCORE%",
    "fps",
    "gpu_name",
    "engine_version",
    "vulkan_driver",
    "resolution",
    "ram",
    "gpu_stats",
    "gpu_temp",
    "cpu_stats",
    "cpu_temp",
    "core_load",
)
_HUD_GAME_LINES = (
    "background_alpha=0",
    "legacy_layout=false",
    "font_size=32",
    "image_max_width=200",
    "image=%THUMBNAIL%",
    "custom_text=%GAMENAME%",
    "custom_text=%SYSTEMNAME%",
    "custom_text=%EMULATORCORE%",
)


def _protect_str(string: str | Path | None) -> str:
    """Convert a value to a string, mapping None to an empty string."""
    if string is None:
        return ""
    return str(string)


def get_hud_config(
    system: Emulator,
    system_name: str | None,
    emulator: str,
    core: str | None,
    bezel: Path | None,
) -> str:
    """Build the MangoHud configuration text for the current game."""
    configstr = ""

    if bezel is not None:
        configstr = f"background_image={_protect_str(bezel)}\nlegacy_layout=false\n"

    mode = system.config.get("hud", "none")
    if mode == "none":
        return configstr + "background_alpha=0\n"  # hide the background

    hud_position = _HUD_POSITIONS.get(system.config.get("hud_corner", ""), "bottom-left")

    emulator_str = emulator
    if core and core != emulator:
        emulator_str += f"/{core}"

    # predefined values
    if mode == "perf":
        configstr += f"position={hud_position}\n" + "\n".join(_HUD_PERF_LINES) + "\n"
    elif mode == "game":
        configstr += f"position={hud_position}\n" + "\n".join(_HUD_GAME_LINES)
    elif mode == "custom" and (hud_custom := system.config.get_str("hud_custom")):
        configstr += hud_custom.replace("\\n", "\n")
    else:
        configstr += "background_alpha=0\n"  # hide the background

    replacements = {
        "%SYSTEMNAME%": system_name,
        "%GAMENAME%": system.es_game_info.get("name", ""),
        "%EMULATORCORE%": emulator_str,
        "%THUMBNAIL%": system.es_game_info.get("thumbnail", ""),
    }
    for placeholder, value in replacements.items():
        configstr = configstr.replace(placeholder, _protect_str(value))
    return configstr


def _resolve_mangohud_binary() -> Path | None:
    """Resolve which MangoHud binary to use for the HUD overlay.

    Retrobox ships its own MangoHud build (with bezel support) under
    MANGOHUD_BIN, kept in a private prefix so it never shadows a
    system-wide install. That bundled build is preferred; if it's
    missing, fall back to whatever "mangohud" is on PATH (which may or
    may not support bezels); if neither is available, the HUD overlay
    is skipped entirely rather than failing the launch.

    Returns:
        The Path to the MangoHud binary to use, or None if none is
        available.
    """
    if MANGOHUD_BIN.is_file() and os.access(MANGOHUD_BIN, os.X_OK):
        return MANGOHUD_BIN

    if system_mangohud := shutil.which("mangohud"):
        _logger.warning(
            "Bundled MangoHud not found at %s, falling back to the system "
            "'mangohud' (bezel support may not be available).",
            MANGOHUD_BIN,
        )
        return Path(system_mangohud)

    return None


_DEFAULT_XDG_DATA_DIRS = "/usr/local/share:/usr/share"


def _expose_vulkan_layer(cmd: Command) -> None:
    """Make the Vulkan loader find the bundled MangoHud implicit layer.

    The layer's manifest lives in the private prefix
    (MANGOHUD_VULKAN_LAYER_DIR), which is on none of the loader's search
    paths: without help, the loader never sees the layer and Vulkan games
    get no HUD even though RETROBOX_MANGOHUD=1 is set. (OpenGL works
    because it goes through the "mangohud --dlsym" wrapper, not a layer.)

    The loader reads implicit layers from "<dir>/vulkan/implicit_layer.d"
    for every <dir> in XDG_DATA_DIRS, in every loader version, so the
    prefix's share/ is appended to it. The newer VK_ADD_IMPLICIT_LAYER_PATH
    would be cleaner but is missing from older loaders (Ubuntu 24.04 ships
    1.3.275, which lacks it). It goes last, and the prefix only holds
    vulkan/, so nothing else that reads XDG_DATA_DIRS is affected.
    """
    if not MANGOHUD_VULKAN_LAYER_DIR.is_dir():
        _logger.warning(
            "MangoHud Vulkan layer directory %s not found: Vulkan games will get no HUD",
            MANGOHUD_VULKAN_LAYER_DIR,
        )
        return

    share = str(MANGOHUD_PREFIX_DIR / "share")
    current = cmd.env.get("XDG_DATA_DIRS") or os.environ.get("XDG_DATA_DIRS") or _DEFAULT_XDG_DATA_DIRS
    if share in str(current).split(":"):
        return
    cmd.env["XDG_DATA_DIRS"] = f"{current}:{share}"


def _configure_mangohud_env(cmd: Command, mangohud_bin: Path) -> None:
    """Set the environment variables that drive the MangoHud Vulkan layer.

    There are two distinct MangoHud installs that can be in play:

    - The bundled retrobox build (bezel/background_image support),
      registered under its own "RETROBOX_MANGOHUD" implicit layer so it
      never collides with a system-wide install.
    - Whatever system-wide "mangohud" (apt/dnf, etc.) might be
      installed, registered under the vanilla "MANGOHUD" implicit
      layer, with no bezel support.

    Only one should ever be enabled for a given launch, and the other
    one's implicit layer must be actively disabled -- not left alone --
    so it can't "conquer" a process retrobox is trying to overlay.

    Important Vulkan Loader gotcha: a layer's "disable_environment"
    check is presence-only, not value-based. Setting a variable to "0"
    still counts as "present" and forces the layer off regardless of
    any other variable. So to truly enable a layer, its own *_DISABLE
    variable must be entirely absent from the child's environment, not
    merely set to a falsy value. cmd.env supports this via a None
    sentinel: run_command() strips any key whose value is None from the
    environment it hands to the child process, instead of just setting
    it to "0".

    Args:
        cmd: The Command whose env will be updated in place.
        mangohud_bin: The MangoHud binary resolved by
            _resolve_mangohud_binary(), used to tell which of the two
            installs is actually going to run.
    """
    if mangohud_bin == MANGOHUD_BIN:
        # Bundled retrobox build: drive it via its own layer, and force
        # the system layer off.
        cmd.env["RETROBOX_MANGOHUD"] = "1"
        cmd.env["RETROBOX_MANGOHUD_DISABLE"] = None
        cmd.env["MANGOHUD"] = "0"
        cmd.env["DISABLE_MANGOHUD"] = "1"
        _expose_vulkan_layer(cmd)
    else:
        # Fell back to whatever "mangohud" is on PATH. That build has
        # no notion of RETROBOX_MANGOHUD, and doesn't carry the
        # background_image/bezel patch, so this is a best-effort
        # overlay without bezel support.
        _logger.info(
            "Using the system MangoHud install for the HUD overlay "
            "(bezel/background image will not be rendered)."
        )
        cmd.env["MANGOHUD"] = "1"
        cmd.env["DISABLE_MANGOHUD"] = None
        cmd.env["RETROBOX_MANGOHUD"] = "0"
        cmd.env["RETROBOX_MANGOHUD_DISABLE"] = "1"

    cmd.env["MANGOHUD_CONFIGFILE"] = str(HUD_CONFIG_FILE)


def setup_hud(session: GameSession, cmd: Command) -> None:
    """Configure the MangoHud overlay (HUD and bezel) for the command, if enabled."""
    system = session.system
    if not system.config.get_bool("hud_support"):
        return

    # these emulators handle MangoHud themselves (cemu, openmsx), and the HUD and
    # the bezel cause game issues there: leave them out
    if session.generator.hasInternalMangoHUDCall():
        _logger.debug("skipping the HUD overlay: %s calls MangoHud itself", system.config.emulator)
        return

    hud_bezel = get_hud_bezel(system, session.generator, session.rom, session.resolution)

    hud = system.config.get("hud")
    hud_enabled = bool(hud) and hud.lower() != "none"
    if not hud_enabled and hud_bezel is None:
        return

    mangohud_bin = _resolve_mangohud_binary()
    if mangohud_bin is None:
        _logger.info(
            "Skipping the HUD overlay: no usable MangoHud installation found (bundled or system)."
        )
        return

    _configure_mangohud_env(cmd, mangohud_bin)

    hud_config = get_hud_config(
        system,
        session.args.systemname,
        system.config.emulator,
        effective_core(system),
        hud_bezel,
    )
    HUD_CONFIG_FILE.write_text(hud_config, encoding="utf-8")

    if session.generator.usesOpenGLDirectPreload(system.config):
        # OpenGL: run through the mangohud wrapper in dlsym-hook mode. The
        # installed wrapper now hardcodes the real lib64 path instead of
        # relying on ld.so to expand "$LIB" (several launchers, including
        # sharun-wrapped emulators, never expand it), so "mangohud --dlsym"
        # is safe to use again instead of setting LD_PRELOAD by hand here.
        cmd.array = [str(mangohud_bin), "--dlsym", *cmd.array]

    # Vulkan: the implicit layer is switched on by the environment set in
    # _configure_mangohud_env() (RETROBOX_MANGOHUD=1 for the bundled build,
    # MANGOHUD=1 for the system one) and, for the bundled build, made
    # visible to the loader by _expose_vulkan_layer(). We deliberately do NOT
    # prepend the mangohud binary to cmd.array here, since doing so triggers
    # a fatal "eglStreamPostD3DTextureANGLE" error on Asahi.
