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
    MANGOHUD_LEGACY_VULKAN_LAYER_DIR,
    MANGOHUD_VULKAN_LAYER_DIR,
    MANGOHUD_VULKAN_MANIFEST_GLOB,
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
_DEFAULT_XDG_CONFIG_DIRS = "/etc/xdg"


def _child_env(cmd: Command, key: str) -> str:
    """Value of an environment variable as the child process will see it."""
    if key in cmd.env:
        return str(cmd.env[key] or "")
    return os.environ.get(key, "")


def _loader_layer_dirs(cmd: Command) -> list[Path]:
    """Implicit layer directories, in the order the Vulkan loader searches them.

    Mirrors the loader on Linux: XDG_CONFIG_HOME, XDG_CONFIG_DIRS, /etc,
    XDG_DATA_HOME, XDG_DATA_DIRS, each with "vulkan/implicit_layer.d"
    appended. When two manifests declare the same layer name, the loader
    keeps the first one it finds, so an old copy in a directory searched
    earlier hides the packaged one.
    """
    home = Path.home()
    bases: list[str] = [_child_env(cmd, "XDG_CONFIG_HOME") or str(home / ".config")]
    bases += (_child_env(cmd, "XDG_CONFIG_DIRS") or _DEFAULT_XDG_CONFIG_DIRS).split(":")
    bases.append("/etc")
    bases.append(_child_env(cmd, "XDG_DATA_HOME") or str(home / ".local" / "share"))
    bases += (_child_env(cmd, "XDG_DATA_DIRS") or _DEFAULT_XDG_DATA_DIRS).split(":")

    dirs: list[Path] = []
    for base in bases:
        if not base:
            continue
        layer_dir = Path(base) / "vulkan" / "implicit_layer.d"
        if layer_dir not in dirs:
            dirs.append(layer_dir)
    return dirs


def _warn_shadowing_manifests(cmd: Command) -> None:
    """Warn about stale Retrobox layer manifests that hide the packaged one."""
    for layer_dir in _loader_layer_dirs(cmd):
        if layer_dir == MANGOHUD_VULKAN_LAYER_DIR:
            return
        for manifest in sorted(layer_dir.glob(MANGOHUD_VULKAN_MANIFEST_GLOB)):
            _logger.warning(
                "%s is found by the Vulkan loader before the one in %s and hides "
                "it: Vulkan games load whatever library it points to. Remove it "
                "unless it is intentional.",
                manifest,
                MANGOHUD_VULKAN_LAYER_DIR,
            )


def _expose_vulkan_layer(cmd: Command) -> None:
    """Make sure the Vulkan loader finds the bundled MangoHud implicit layer.

    Current retrobox-mangohud packages install the layer manifest in
    MANGOHUD_VULKAN_LAYER_DIR (/usr/share/vulkan/implicit_layer.d), which
    the loader always searches: nothing has to be added to the environment,
    only RETROBOX_MANGOHUD=1 (see _configure_mangohud_env()). Stale copies of
    the manifest in directories the loader searches first are reported,
    because they win over the packaged one.

    Older packages kept the manifest inside the private prefix, on none of
    the loader's search paths. For those, the prefix's share/ is appended
    to XDG_DATA_DIRS (the loader reads "<dir>/vulkan/implicit_layer.d" for
    every entry, in every loader version; VK_ADD_IMPLICIT_LAYER_PATH is
    missing from older loaders such as Ubuntu 24.04's 1.3.275).
    """
    if any(MANGOHUD_VULKAN_LAYER_DIR.glob(MANGOHUD_VULKAN_MANIFEST_GLOB)):
        _warn_shadowing_manifests(cmd)
        return

    if any(MANGOHUD_LEGACY_VULKAN_LAYER_DIR.glob(MANGOHUD_VULKAN_MANIFEST_GLOB)):
        share = str(MANGOHUD_LEGACY_VULKAN_LAYER_DIR.parent.parent)
        current = _child_env(cmd, "XDG_DATA_DIRS") or _DEFAULT_XDG_DATA_DIRS
        if share not in current.split(":"):
            cmd.env["XDG_DATA_DIRS"] = f"{current}:{share}"
        return

    _logger.warning(
        "No %s found in %s (nor in the legacy %s): Vulkan games will get no HUD",
        MANGOHUD_VULKAN_MANIFEST_GLOB,
        MANGOHUD_VULKAN_LAYER_DIR,
        MANGOHUD_LEGACY_VULKAN_LAYER_DIR,
    )


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
