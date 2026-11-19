"""What EmulationStation's QUIT entry of the main menu opens.

EmulationStation shows either a single "Really quit?" question (its
``ShowOnlyExit`` setting, which retrobox-emulationstation turns on by default,
as a program on a desktop) or batocera's full quit menu: restart, suspend,
shut down, fast shut down and quit EmulationStation. Its own switch for it
only exists on Windows, so Retrobox sets it from retrobox.ini before
EmulationStation starts::

    [core]
    full_quit_menu = true
"""

from __future__ import annotations

import logging
from pathlib import Path

from retrobox.paths import ES_SETTINGS_CFG, get_ini_value
from retrobox.utils.es_settings import write_es_setting

_logger = logging.getLogger(__name__)

_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})


def full_quit_menu() -> bool:
    """Whether retrobox.ini asks for the full quit menu (``[core] full_quit_menu``)."""
    return get_ini_value("core", "full_quit_menu", "false").lower() in _TRUE_VALUES


def apply_quit_menu(settings_path: Path = ES_SETTINGS_CFG) -> bool:
    """Write the quit menu retrobox.ini asks for into es_settings.cfg.

    EmulationStation must not be running: it rewrites the file when it exits.

    Returns:
        True if the file changed.
    """
    full = full_quit_menu()
    changed = write_es_setting(settings_path, "bool", "ShowOnlyExit", "false" if full else "true")
    if changed:
        _logger.info("Quit menu: %s", "full (restart, shut down...)" if full else "quit only")
    return changed
