"""Run the setup screen from Retrobox (the launcher and the startup).

The screen itself knows nothing about Retrobox's paths: everything comes on
its command line. This module builds the part every caller shares (language,
fonts of the EmulationStation theme, icon, window class, background) and runs
it. Only lightweight modules are imported here; SDL and Pillow are loaded by
the screen's own process.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING, Final

from retrobox.paths import (
    ES_RESOURCE_DIRS,
    ES_SETTINGS_CFG,
    ES_WM_CLASS,
    FRONTEND_DIR,
    SHARE_DIR,
    THEMES_DIR,
    layered_file,
)
from retrobox.utils.es_settings import confirm_is_east, read_es_settings

from . import EXIT_UNAVAILABLE
from .i18n import pick_language
from .theme import find_theme, theme_fonts

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

_logger = logging.getLogger(__name__)

# overridable like any shared file: /etc/retrobox/<path> or ~/.config/retrobox/<path>
BACKGROUND: Final = "emusetup/background.png"
# the logo of the application menu entry
ICON: Final = SHARE_DIR / "icons" / "retrobox_logo.png"


def look_arguments() -> list[str]:
    """Language, fonts (from the EmulationStation theme), confirm button, icon,
    window class and background of the screen."""
    settings = read_es_settings(ES_SETTINGS_CFG)
    language = pick_language(settings.get("Language", ""))
    theme = find_theme((FRONTEND_DIR / "themes", THEMES_DIR), settings.get("ThemeSet", ""))
    fonts = theme_fonts(theme, settings, ES_RESOURCE_DIRS, language)
    _logger.debug("setup screen: language %s, theme %s, fonts %s", language, theme, fonts)

    arguments = ["--lang", language, "--wm-class", ES_WM_CLASS]
    if confirm_is_east(settings):  # the same confirm button as EmulationStation
        arguments.append("--confirm-east")
    if fonts.menu is not None:
        arguments += ["--menu-font", str(fonts.menu)]
    if fonts.help is not None:
        arguments += ["--help-font", str(fonts.help)]
    if ICON.is_file():
        arguments += ["--icon", str(ICON)]
    background = layered_file(BACKGROUND)
    if background is not None:
        arguments += ["--background", str(background)]
    return arguments


def run_screen(
    label: str, log_path: Path, command: Sequence[str], extra: Sequence[str] = ()
) -> int:
    """Show the screen running ``command`` and wait for it.

    Args:
        label: What is installed or downloaded, as shown to the user.
        log_path: Where the output of ``command`` is saved.
        command: The installer or downloader to run.
        extra: More arguments for the screen (``--download``, pad mapping...).

    Returns:
        The screen's exit status (see the package docstring); EXIT_UNAVAILABLE
        if it couldn't even be started.
    """
    screen = [sys.executable, "-m", "retrobox.emusetup", "--label", label,
              "--log", str(log_path), *look_arguments(), *extra, "--", *command]
    try:
        status = subprocess.run(screen, check=False).returncode
    except OSError:
        _logger.exception("cannot start the setup screen")
        return EXIT_UNAVAILABLE
    _logger.debug("setup screen exited with status %s", status)
    return status
