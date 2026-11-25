"""Where Kodi is: Retrobox's install (a build, or the marker of its Flatpak),
any Flatpak of Kodi, or the distribution's package.

Kodi is the one program whose Flatpak counts: ``bin/retrobox-kodi`` starts it
(and configgen writes its controllers in the Flatpak's userdata), so the
installer (``tools/emulators/kodi.sh``) installs the Flathub one on x86_64.
That install leaves a marker in ``<emulators>/kodi/app`` instead of a program,
which is what the launcher and the update screen look for.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from retrobox.configgen.utils.emulator_binary import EmulatorBinary

FLATPAK_ID: Final = "tv.kodi.Kodi"
# what tools/lib/installer.sh's flatpak_install leaves in app/
FLATPAK_MARKER: Final = ".retrobox-flatpak"


def flatpak_installed(app: str = FLATPAK_ID) -> Path | None:
    """The ``flatpak`` command when ``app`` is installed (for any user), else None."""
    flatpak = shutil.which("flatpak")
    if flatpak is None:
        return None
    try:
        result = subprocess.run(
            [flatpak, "info", app], capture_output=True, check=False, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(flatpak) if result.returncode == 0 else None


@dataclass(frozen=True)
class KodiBinary(EmulatorBinary):
    """Kodi's executable: an :class:`EmulatorBinary` that also takes its Flatpak."""

    def find_in(self, directory: Path) -> Path | None:
        """A build in ``directory``, or its Flatpak marker when that Flatpak is there."""
        if (found := super().find_in(directory)) is not None:
            return found
        marker = directory / "app" / FLATPAK_MARKER
        if marker.is_file() and flatpak_installed() is not None:
            return marker
        return None

    def find(self) -> Path | None:
        """Retrobox's install, else any Kodi Flatpak, else the package's ``kodi``."""
        if (found := self.find_in(self.directory)) is not None:
            return found
        if (flatpak := flatpak_installed()) is not None:
            return flatpak
        return super().find()


KODI: Final = KodiBinary(folder="kodi", names=("kodi",), installer="kodi", appimage=False)
