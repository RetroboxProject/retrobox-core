"""Base class of the emulator generators."""

# The method and argument names are the interface every generator implements.
# pylint: disable=invalid-name

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING

from retrobox.configgen.exceptions import RetroboxException
from retrobox.launcher.game_state import DEFAULT_EXIT_TIMEOUT

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from ..typedefs import DeviceInfoMapping, Resolution
    from ..Command import Command
    from ..config import SystemConfig
    from ..controller import Controllers
    from ..Emulator import Emulator
    from ..gun import Guns
    from ..hotkeys import Bindings

# pylint: disable=unused-argument  # the defaults ignore what the overrides use


class Generator(metaclass=ABCMeta):
    """What the launcher needs from the generator of an emulator."""

    @abstractmethod
    def generate(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        system: Emulator,
        rom: Path,
        playersControllers: Controllers,
        metadata: Mapping[str, str],
        guns: Guns,
        wheels: DeviceInfoMapping,
        gameResolution: Resolution,
    ) -> Command:
        """Write the emulator configuration and return the command to run it."""

    def check_if_exists(self, what: Path, emuname: str) -> None:
        """Raise a RetroboxException if a path the emulator needs does not exist."""
        if not what.exists():
            raise RetroboxException(f"Path for {emuname} does not exist: {what}")

    def getResolutionMode(self, config: SystemConfig) -> str:
        """Return the video mode the emulator runs in."""
        return config["videomode"]

    def getMouseMode(self, config: SystemConfig, rom: Path) -> bool:
        """Tell whether the emulator needs the mouse."""
        return False

    def executionDirectory(self, config: SystemConfig, rom: Path) -> Path | None:
        """Return the folder to run the emulator from, or None to keep the current one."""
        return None

    def writesToRom(self, config: SystemConfig) -> bool:
        """Tell whether the emulator writes into the ROM area (DOS, Amiga and Wine do)."""
        return False

    def supportsInternalBezels(self) -> bool:
        """Tell whether the emulator draws its own bezels (MAME, libretro).

        When it does, the one of MangoHud is not displayed.
        """
        return False

    def allows_bezel(self, config: SystemConfig) -> bool:
        """Tell whether a bezel image can be drawn over this emulator.

        Override it when the emulator forces a ratio or a stretch the bezel
        does not fit. Only the bezel image is dropped: ``force_no_bezel`` is
        for the user, to drop everything.
        """
        return True

    def hasInternalMangoHUDCall(self) -> bool:
        """Tell whether the generator handles MangoHud itself (cemu, openmsx).

        The launcher then draws neither the HUD nor the bezel.
        """
        return False

    def getInGameRatio(self, config: SystemConfig, gameResolution: Resolution, rom: Path) -> float:
        """Return the aspect ratio of the game image (generators should override it)."""
        return 4 / 3

    def usesOpenGLDirectPreload(self, config) -> bool:
        """Tell whether MangoHud must be preloaded for an OpenGL emulator."""
        return False

    def exit_env(self, system: Emulator, rom: Path) -> Mapping[str, Sequence[str]]:
        """Environment variables, and their values, that mark the game's processes.

        Only needed when the game is started by a client that may already run
        (Steam, Heroic, Lutris): its processes are then not in the emulator's
        process group, and ``retrobox-emukill`` finds them by environment.
        Called after ``generate()``.
        """
        return {}

    def exit_timeout(self, config: SystemConfig) -> float:
        """Seconds the game has to quit after SIGTERM before it is killed."""
        return DEFAULT_EXIT_TIMEOUT

    def savestates(self, system: Emulator, rom: Path) -> dict[str, object] | None:
        """Where the game's save states are and how to ask for them, for the overlay.

        None when the overlay cannot manage the emulator's save states. Else
        ``control`` (the command pipe, see ``Command.stdin_fifo``), ``dir``
        and ``name`` (states are ``<dir>/<name>.state<N>``, with a
        ``.png`` preview next to them) and ``slot`` (the emulator's slot when
        the game starts). Called after ``generate()``.
        """
        return None

    def hotkey_bindings(self, system: Emulator) -> Bindings:
        """How the emulator performs the standard hotkey actions.

        Added to (or replacing) ``hotkeys.common_bindings()``: leaving the
        game, screenshots and the overlay work everywhere without this. Map
        an action to ``None`` to leave its combination free, to ``Native``
        when the generator writes the combination into the emulator's own
        configuration.
        """
        return {}
