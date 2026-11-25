"""Offer to install the emulator of a game when it is missing, or again on request.

Only emulators with an installer in ``tools/emulators/`` are handled. Whether
one is installed is decided by the same :class:`EmulatorBinary` its generator
runs, read from the generator's own paths module so the two never drift
apart: an emulator found anywhere (Retrobox's install, an AppImage of the
user, the distribution's package) is not offered again. The screen itself is
the overlay's task screen (``retrobox-overlay --task``), a process of its own:
the launcher just waits for its verdict. Without the overlay nothing is
offered or installed (the emulators are then installed and updated by hand,
``retrobox --install-emulator``) and the game is launched anyway.

When the launcher asks for a reinstall (L1 and R1, or Ctrl and Shift, held while the game starts),
the screen offers to install the emulator again even though it is there, to
update it. That install goes through ``emulator_update``, which builds the
new version in a separate folder and only replaces the installed one once it
works; whatever the answer or the outcome, the game is launched afterwards.
"""

from __future__ import annotations

import logging
import sys
from importlib import import_module
from typing import Final, NamedTuple

from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.paths import BIN_DIR, LOGS, RETROBOX_ROOTDIR
from retrobox.utils.overlay_task import EXIT_DECLINED, EXIT_FAILED, run_task

_logger = logging.getLogger(__name__)

# what a reinstall keeps from the installed folder by default (relative to it)
_KEEP_DEFAULT: Final = ("config",)


class Installable(NamedTuple):
    """An emulator Retrobox can install, and how a reinstall treats its folder."""

    installer: str  # tools/emulators/<installer>.sh
    label: str
    module: str  # under retrobox.configgen.generators
    attribute: str  # the EmulatorBinary of the generator, in that module
    # paths inside <emulators>/<folder> whose installed copy survives a
    # reinstall, winning over what the installer ships (user-edited configuration...)
    keep: tuple[str, ...] = _KEEP_DEFAULT


_RETROARCH = Installable("retroarch", "RetroArch", "libretro.libretroPaths", "RETROARCH")
_DOLPHIN = Installable("dolphin-emu", "Dolphin", "dolphin.dolphin_paths", "DOLPHIN")
_EDEN = Installable("eden", "Eden", "eden.edenPaths", "EDEN")
_RYUJINX = Installable("ryujinx", "Ryujinx", "ryujinx.ryujinxPaths", "RYUJINX")

# emulator name (as in the systems' yaml) -> installer
_INSTALLABLE: Final[dict[str, Installable]] = {
    "libretro": _RETROARCH,
    "ares": Installable("ares", "ares", "ares.ares_paths", "ARES"),
    "cemu": Installable("cemu", "Cemu", "cemu.cemuPaths", "CEMU"),
    "dolphin": _DOLPHIN,
    "dolphin-emu": _DOLPHIN,
    "eden": _EDEN,
    "eden-emu": _EDEN,
    "flycast": Installable("flycast", "Flycast", "flycast.flycastPaths", "FLYCAST"),
    "mupen64plus": Installable(
        "mupen64plus", "Mupen64Plus", "mupen64plus.mupen64plus_paths", "MUPEN64PLUS"
    ),
    "pcsx2": Installable("pcsx2", "PCSX2", "pcsx2.pcsx2_paths", "PCSX2"),
    "ppsspp": Installable("ppsspp", "PPSSPP", "ppsspp.ppssppPaths", "PPSSPP"),
    "redream": Installable(
        "redream", "Redream", "redream.redream_paths", "REDREAM", keep=("redream.cfg",)
    ),
    "rpcs3": Installable("rpcs3", "RPCS3", "rpcs3.rpcs3Paths", "RPCS3"),
    "ryujinx": _RYUJINX,
    "ryujinx-emu": _RYUJINX,
    "keisho": Installable("keisho", "Keisho", "keisho.keisho_paths", "KEISHO"),
    # the apps system's Kodi (and EmulationStation's Kodi entry): the Flatpak on
    # x86_64, a build elsewhere; its data is in ~/.kodi or the Flatpak's, not app/
    "kodi": Installable("kodi", "Kodi", "kodi.kodi_paths", "KODI", keep=()),
    "supermodel": Installable(
        "supermodel3", "Supermodel", "supermodel.supermodel_paths", "SUPERMODEL",
        keep=("Config/Supermodel.ini", "NVRAM", "Saves"),
    ),
    "vita3k": Installable("vita3k", "Vita3K", "vita3k.vita3k_paths", "VITA3K"),
}


def installable(emulator: str) -> Installable | None:
    """The installer entry of ``emulator`` (as in the systems' yaml), if it has one."""
    return _INSTALLABLE.get(emulator)


def installables() -> list[Installable]:
    """Every emulator Retrobox can install, once each, by installer name."""
    unique = {entry.installer: entry for entry in _INSTALLABLE.values()}
    return [unique[name] for name in sorted(unique)]


def detector_of(entry: Installable) -> EmulatorBinary | None:
    """How the generator of ``entry`` finds its executable (None if it can't be read)."""
    try:
        module = import_module(f"retrobox.configgen.generators.{entry.module}")
        detector = getattr(module, entry.attribute)
    except (ImportError, AttributeError):
        _logger.exception("cannot locate the executable of %s", entry.label)
        return None
    return detector if isinstance(detector, EmulatorBinary) else None


def _installer_available(entry: Installable) -> bool:
    return (RETROBOX_ROOTDIR / "tools" / "emulators" / f"{entry.installer}.sh").is_file()


def _missing(emulator: str) -> Installable | None:
    """The installer of ``emulator`` when it can be installed and is not found anywhere."""
    entry = _INSTALLABLE.get(emulator)
    if entry is None:
        return None
    detector = detector_of(entry)
    if detector is None or detector.find() is not None:
        return None
    if not _installer_available(entry):
        _logger.warning("%s is missing and its installer is not available", entry.label)
        return None
    return entry


def _reinstall(emulator: str) -> None:
    """Offer to install ``emulator`` again (Retrobox's own copy), safely."""
    entry = _INSTALLABLE.get(emulator)
    if entry is None or not _installer_available(entry):
        _logger.info("reinstall requested, but %s has no installer in Retrobox", emulator)
        return
    _logger.info("reinstall of %s requested (chord held)", entry.label)
    status = run_task(
        entry.label,
        LOGS / f"emusetup-{entry.installer}.log",
        [sys.executable, "-m", "retrobox.launcher.emulator_update", emulator],
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
    entry = _missing(emulator)
    if entry is None:
        if reinstall:
            _reinstall(emulator)
        return True
    _logger.info("%s is not installed: offering to install it", entry.label)

    status = run_task(
        entry.label,
        LOGS / f"emusetup-{entry.installer}.log",
        [str(BIN_DIR / "retrobox"), "--install-emulator", entry.installer],
    )
    _logger.info("emulator setup screen exited with status %s", status)
    # installed, or no screen at all (any other status): go on with the launch
    return status not in (EXIT_DECLINED, EXIT_FAILED)
