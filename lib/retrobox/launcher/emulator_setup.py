"""Offer to install the emulator of a game when it is missing.

Only emulators with an installer in ``tools/emulators/`` are handled: for
each one, the file whose absence means "not installed" is the very binary its
generator runs, read from the generator's own paths module so the two never
drift apart. The screen itself (``retrobox.emusetup``) runs in a child
process; the launcher just waits for its verdict.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

from retrobox.configgen.controller import Controller
from retrobox.paths import BIN_DIR, LOGS, RETROBOX_ROOTDIR, layered_file

if TYPE_CHECKING:
    from retrobox.configgen.controller import Controllers

_logger = logging.getLogger(__name__)

# overridable like any shared file: /etc/retrobox/<path> or ~/.config/retrobox/<path>
BACKGROUND: Final = "emusetup/background.png"

_EXIT_DECLINED: Final = 10
_EXIT_FAILED: Final = 11
# es_input.cfg inputs the screen uses
_PAD_INPUTS: Final = ("a", "b", "up", "down", "left", "right", "joystick1up", "joystick1left")


class _Installable(NamedTuple):
    installer: str  # tools/emulators/<installer>.sh
    label: str
    module: str  # under retrobox.configgen.generators
    attribute: str  # the Path constant of the binary (or of its folder)
    relative: str = ""  # appended to the constant


_RETROARCH = _Installable("retroarch", "RetroArch", "libretro.libretroPaths", "_RETROARCH_BIN")
_DOLPHIN = _Installable("dolphin-emu", "Dolphin", "dolphin.dolphin_paths", "DOLPHIN_BIN")
_EDEN = _Installable("eden", "Eden", "eden.edenPaths", "EDEN_BIN")
_RYUJINX = _Installable("ryujinx", "Ryujinx", "ryujinx.ryujinxPaths", "RYUJINX_BIN")

# emulator name (as in the systems' yaml) -> installer
_INSTALLABLE: Final[dict[str, _Installable]] = {
    "libretro": _RETROARCH,
    "ares": _Installable("ares", "ares", "ares.ares_paths", "ARES_BIN"),
    "cemu": _Installable("cemu", "Cemu", "cemu.cemuPaths", "CEMU_BIN"),
    "dolphin": _DOLPHIN,
    "dolphin-emu": _DOLPHIN,
    "eden": _EDEN,
    "eden-emu": _EDEN,
    "flycast": _Installable("flycast", "Flycast", "flycast.flycastPaths", "FLYCAST_BIN"),
    "model2emu": _Installable(
        "model2emu", "Model 2 Emulator", "model2emu.model2emuPaths", "M2EMU_EMUDIR",
        "emulator_multicpu.exe",
    ),
    "pcsx2": _Installable("pcsx2", "PCSX2", "pcsx2.pcsx2_paths", "PCSX2_BIN"),
    "ppsspp": _Installable("ppsspp", "PPSSPP", "ppsspp.ppssppPaths", "PPSSPP_BIN"),
    "redream": _Installable("redream", "Redream", "redream.redream_paths", "REDREAM_BIN"),
    "rpcs3": _Installable("rpcs3", "RPCS3", "rpcs3.rpcs3Paths", "RPCS3_BIN"),
    "ryujinx": _RYUJINX,
    "ryujinx-emu": _RYUJINX,
    "supermodel": _Installable(
        "supermodel3", "Supermodel", "supermodel.supermodel_paths", "SUPERMODEL_BIN"
    ),
    "vita3k": _Installable("vita3k", "Vita3K", "vita3k.vita3k_paths", "VITA3K_BIN"),
}


def _binary_of(entry: _Installable) -> Path | None:
    try:
        module = import_module(f"retrobox.configgen.generators.{entry.module}")
        base = Path(getattr(module, entry.attribute))
    except (ImportError, AttributeError, TypeError):
        _logger.exception("cannot locate the binary of %s", entry.label)
        return None
    return base / entry.relative if entry.relative else base


def _missing(emulator: str) -> tuple[_Installable, Path] | None:
    """The installer and binary of ``emulator`` when it can be installed and is not."""
    entry = _INSTALLABLE.get(emulator)
    if entry is None:
        return None
    binary = _binary_of(entry)
    if binary is None or binary.exists():
        return None
    if not (RETROBOX_ROOTDIR / "tools" / "emulators" / f"{entry.installer}.sh").is_file():
        _logger.warning("%s is missing and its installer is not available", entry.label)
        return None
    return entry, binary


def _pad_arguments(controllers: Controllers) -> list[str]:
    """Player 1's controller and mapping, for the screen."""
    player = Controller.find_player_number(controllers, 1)
    if player is None or player.type != "joystick":
        return []
    arguments = ["--pad-guid", player.guid]
    if player.device_path:
        arguments += ["--pad-device", player.device_path]
    for name in _PAD_INPUTS:
        pad_input = player.inputs.get(name)
        if pad_input is not None and pad_input.type in ("button", "hat", "axis"):
            arguments += ["--pad-map", f"{name}={pad_input.type}:{pad_input.id}:{pad_input.value}"]
    return arguments


def ensure_emulator(emulator: str, controllers: Controllers) -> bool:
    """Offer to install ``emulator`` if it is missing.

    Args:
        emulator: The emulator of the game (``system.config.emulator``).
        controllers: The players' controllers (player 1 drives the screen).

    Returns:
        False when the game must not be launched (the user said no, or the
        installation failed and the user has seen why); True otherwise,
        including when no screen could be shown: the launch then goes on and
        fails the usual way.
    """
    missing = _missing(emulator)
    if missing is None:
        return True
    entry, binary = missing
    _logger.info("%s is not installed (%s): offering to install it", entry.label, binary)

    command = [sys.executable, "-m", "retrobox.emusetup", "--label", entry.label,
               "--log", str(LOGS / f"emusetup-{entry.installer}.log"), "--check", str(binary)]
    background = layered_file(BACKGROUND)
    if background is not None:
        command += ["--background", str(background)]
    command += _pad_arguments(controllers)
    command += ["--", str(BIN_DIR / "retrobox"), "--setup-emulator", entry.installer]

    try:
        status = subprocess.run(command, check=False).returncode
    except OSError:
        _logger.exception("cannot start the emulator setup screen")
        return True

    _logger.info("emulator setup screen exited with status %s", status)
    # installed, or no screen at all (any other status): go on with the launch
    return status not in (_EXIT_DECLINED, _EXIT_FAILED)
