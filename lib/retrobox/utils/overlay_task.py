"""Run installers and downloads on the overlay's task screen.

Retrobox has no screen of its own for them: ``retrobox-overlay --task`` shows
the question, the installer's output (and takes the keyboard for it, e.g. for
a sudo password) and the buttons, with EmulationStation's look. It runs in a
process of its own, so none of it stays resident while a game runs. Without
the overlay installed nothing is run: whoever prefers that installs and
updates the emulators and the default content by hand
(``retrobox --setup-emulator NAME``, ``retrobox --update-default-theme``...).

The overlay also tells whether L1 and R1, or Ctrl and Shift, are held down (``--held``), which is
how a game's start asks for its emulator to be installed again.

Exit status of the screen: 0 done, 10 declined (or a download cancelled),
11 failed, 12 no screen could be opened.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import TYPE_CHECKING, Final

from retrobox.paths import layered_file

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

_logger = logging.getLogger(__name__)

EXIT_INSTALLED: Final = 0
EXIT_DECLINED: Final = 10
EXIT_FAILED: Final = 11
EXIT_UNAVAILABLE: Final = 12

OVERLAY_COMMAND: Final = "retrobox-overlay"
"""The overlay's command, found through ``PATH``."""

# overridable like any shared file: /etc/retrobox/<path> or ~/.config/retrobox/<path>
BACKGROUND: Final = "emusetup/background.png"

_FORCE_REINSTALL: Final = "RETROBOX_REINSTALL_EMULATOR"
_HELD_TIMEOUT_S: Final = 5


def overlay_available() -> bool:
    """Whether the overlay is installed (and so the task screen can be shown)."""
    return shutil.which(OVERLAY_COMMAND) is not None


def run_task(  # pylint: disable=too-many-arguments
    label: str,
    log_path: Path,
    command: Sequence[str],
    *,
    check: Path | None = None,
    download: bool = False,
    reinstall: bool = False,
) -> int:
    """Show the task screen running ``command`` and wait for it.

    Args:
        label: What is installed or downloaded, as shown to the user.
        log_path: Where the output of ``command`` is saved.
        command: The installer or downloader to run.
        check: A file that must exist once ``command`` has worked.
        download: ``command`` downloads ``label``: run it right away and close
            when it works, instead of asking first.
        reinstall: ``label`` is installed: offer to install it again.

    Returns:
        The screen's exit status (see the module docstring); EXIT_UNAVAILABLE
        when the overlay is not installed or could not show the screen.
    """
    overlay = shutil.which(OVERLAY_COMMAND)
    if overlay is None:
        _logger.warning("%s is not installed: nothing to show %s on", OVERLAY_COMMAND, label)
        return EXIT_UNAVAILABLE
    screen = [overlay, "--task", "--label", label, "--log", str(log_path)]
    if check is not None:
        screen += ["--check", str(check)]
    background = layered_file(BACKGROUND)
    if background is not None:
        screen += ["--background", str(background)]
    if download:
        screen.append("--download")
    if reinstall:
        screen.append("--reinstall")
    screen += ["--", *command]
    try:
        status = subprocess.run(screen, check=False).returncode
    except OSError:
        _logger.exception("cannot start the task screen")
        return EXIT_UNAVAILABLE
    _logger.debug("task screen exited with status %s", status)
    if status not in (EXIT_INSTALLED, EXIT_DECLINED, EXIT_FAILED):
        # 12, or an overlay too old to know --task, or a crash
        return EXIT_UNAVAILABLE
    return status


def reinstall_requested() -> bool:
    """True when L1 and R1, or Ctrl and Shift, are held (or the environment variable is set).

    The overlay reads the controllers' state from the kernel, nothing needs a
    window or the focus. Call it right away when a game starts, while the
    button that launched it is likely still down.
    """
    if os.environ.get(_FORCE_REINSTALL, "") not in ("", "0"):
        _logger.info("%s is set: asking for a reinstall", _FORCE_REINSTALL)
        return True
    overlay = shutil.which(OVERLAY_COMMAND)
    if overlay is None:
        return False
    try:
        held = subprocess.run(
            [overlay, "--held"], check=False, timeout=_HELD_TIMEOUT_S, capture_output=True
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        _logger.debug("cannot ask the overlay whether the reinstall chord is held", exc_info=True)
        return False
    if held:
        _logger.info("the reinstall chord is held: asking for a reinstall")
    return held
