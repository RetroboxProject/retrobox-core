"""Offer to install the emulator of a game when it is missing, or again on request.

Only emulators with an installer in ``tools/emulators/`` are handled: for
each one, the file whose absence means "not installed" is the very binary its
generator runs, read from the generator's own paths module so the two never
drift apart. The screen itself is the overlay's task screen
(``retrobox-overlay --task``), a process of its own: the launcher just waits
for its verdict. Without the overlay nothing is offered or installed (the
emulators are then installed and updated by hand, ``retrobox --setup-emulator``)
and the game is launched anyway.

When the launcher asks for a reinstall (L1 and R1 held while the game starts),
the screen offers to install the emulator again even though it is there, to
update it. That install goes through ``emulator_update``, which builds the
new version in a separate folder and only replaces the installed one once it
works; whatever the answer or the outcome, the game is launched afterwards.
"""

from __future__ import annotations

import logging
import sys
from importlib import import_module
from pathlib import Path
from typing import Final, NamedTuple

from retrobox.paths import BIN_DIR, EMULATORS, LOGS, RETROBOX_ROOTDIR
from retrobox.utils.overlay_task import EXIT_DECLINED, EXIT_FAILED, run_task

_logger = logging.getLogger(__name__)

# what a reinstall keeps from the installed folder by default (relative to it)
_KEEP_DEFAULT: Final = ("config",)


class Installable(NamedTuple):
    """An emulator Retrobox can install, and how a reinstall treats its folder."""

    installer: str  # tools/emulators/<installer>.sh
    label: str
    module: str  # under retrobox.configgen.generators
    attribute: str  # the Path constant of the binary (or of its folder)
    relative: str = ""  # appended to the constant
    # folder a reinstall replaces, relative to the emulators directory
    # (default: the first component of the binary's path, <emulators>/<name>)
    unit: str = ""
    # paths inside that folder whose installed copy survives a reinstall,
    # winning over what the installer ships (user-edited configuration...)
    keep: tuple[str, ...] = _KEEP_DEFAULT


_RETROARCH = Installable("retroarch", "RetroArch", "libretro.libretroPaths", "_RETROARCH_BIN")
_DOLPHIN = Installable("dolphin-emu", "Dolphin", "dolphin.dolphin_paths", "DOLPHIN_BIN")
_EDEN = Installable("eden", "Eden", "eden.edenPaths", "EDEN_BIN")
_RYUJINX = Installable("ryujinx", "Ryujinx", "ryujinx.ryujinxPaths", "RYUJINX_BIN")

# emulator name (as in the systems' yaml) -> installer
_INSTALLABLE: Final[dict[str, Installable]] = {
    "libretro": _RETROARCH,
    "ares": Installable("ares", "ares", "ares.ares_paths", "ARES_BIN"),
    "cemu": Installable("cemu", "Cemu", "cemu.cemuPaths", "CEMU_BIN"),
    "dolphin": _DOLPHIN,
    "dolphin-emu": _DOLPHIN,
    "eden": _EDEN,
    "eden-emu": _EDEN,
    "flycast": Installable("flycast", "Flycast", "flycast.flycastPaths", "FLYCAST_BIN"),
    "pcsx2": Installable("pcsx2", "PCSX2", "pcsx2.pcsx2_paths", "PCSX2_BIN"),
    "ppsspp": Installable("ppsspp", "PPSSPP", "ppsspp.ppssppPaths", "PPSSPP_BIN"),
    "redream": Installable(
        "redream", "Redream", "redream.redream_paths", "REDREAM_BIN", keep=("redream.cfg",)
    ),
    "rpcs3": Installable("rpcs3", "RPCS3", "rpcs3.rpcs3Paths", "RPCS3_BIN"),
    "ryujinx": _RYUJINX,
    "ryujinx-emu": _RYUJINX,
    "keisho": Installable("keisho", "Keisho", "keisho.keisho_paths", "KEISHO_BIN"),
    "supermodel": Installable(
        "supermodel3", "Supermodel", "supermodel.supermodel_paths", "SUPERMODEL_BIN",
        keep=("Config", "NVRAM", "Saves"),
    ),
    "vita3k": Installable("vita3k", "Vita3K", "vita3k.vita3k_paths", "VITA3K_BIN"),
}


def installable(emulator: str) -> Installable | None:
    """The installer entry of ``emulator`` (as in the systems' yaml), if it has one."""
    return _INSTALLABLE.get(emulator)


def binary_of(entry: Installable) -> Path | None:
    """The binary the generator of ``entry`` runs (None if it can't be found)."""
    try:
        module = import_module(f"retrobox.configgen.generators.{entry.module}")
        base = Path(getattr(module, entry.attribute))
    except (ImportError, AttributeError, TypeError):
        _logger.exception("cannot locate the binary of %s", entry.label)
        return None
    return base / entry.relative if entry.relative else base


def unit_of(entry: Installable, relative_binary: Path) -> Path:
    """The folder a reinstall of ``entry`` replaces, relative to the emulators directory."""
    return Path(entry.unit) if entry.unit else Path(relative_binary.parts[0])


def _installer_available(entry: Installable) -> bool:
    return (RETROBOX_ROOTDIR / "tools" / "emulators" / f"{entry.installer}.sh").is_file()


def _missing(emulator: str) -> tuple[Installable, Path] | None:
    """The installer and binary of ``emulator`` when it can be installed and is not."""
    entry = _INSTALLABLE.get(emulator)
    if entry is None:
        return None
    binary = binary_of(entry)
    if binary is None or binary.exists():
        return None
    if not _installer_available(entry):
        _logger.warning("%s is missing and its installer is not available", entry.label)
        return None
    return entry, binary


def _reinstall(emulator: str) -> None:
    """Offer to install the (installed) ``emulator`` again, safely."""
    entry = _INSTALLABLE.get(emulator)
    binary = binary_of(entry) if entry else None
    if entry is None or binary is None or not _installer_available(entry):
        _logger.info("reinstall requested, but %s has no installer in Retrobox", emulator)
        return
    try:
        binary.relative_to(EMULATORS)
    except ValueError:
        _logger.warning("%s is outside %s: it can't be reinstalled safely", binary, EMULATORS)
        return
    _logger.info("reinstall of %s requested (L1 and R1 held)", entry.label)
    status = run_task(
        entry.label,
        LOGS / f"emusetup-{entry.installer}.log",
        [sys.executable, "-m", "retrobox.launcher.emulator_update", emulator],
        check=binary,
        reinstall=True,
    )
    _logger.info("emulator reinstall screen exited with status %s", status)


def ensure_emulator(emulator: str, reinstall: bool = False) -> bool:
    """Offer to install ``emulator`` if it is missing, or again if asked to.

    Args:
        emulator: The emulator of the game (``system.config.emulator``).
        reinstall: Offer to install it again even if it is installed (L1 and
            R1 were held). A reinstall never stops the launch: when it is
            declined or fails, the installed version is still there.

    Returns:
        False when the game must not be launched (the user said no, or the
        installation failed and the user has seen why); True otherwise,
        including when no screen could be shown (no overlay installed): the
        launch then goes on and fails the usual way.
    """
    missing = _missing(emulator)
    if missing is None:
        if reinstall:
            _reinstall(emulator)
        return True
    entry, binary = missing
    _logger.info("%s is not installed (%s): offering to install it", entry.label, binary)

    status = run_task(
        entry.label,
        LOGS / f"emusetup-{entry.installer}.log",
        [str(BIN_DIR / "retrobox"), "--setup-emulator", entry.installer],
        check=binary,
    )
    _logger.info("emulator setup screen exited with status %s", status)
    # installed, or no screen at all (any other status): go on with the launch
    return status not in (EXIT_DECLINED, EXIT_FAILED)
