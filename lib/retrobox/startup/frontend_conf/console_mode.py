"""Console mode: EmulationStation as a console's only screen, not a program to quit.

On (``[core] console_mode = true`` in retrobox.ini), QUIT in EmulationStation's
main menu opens batocera's full quit menu (restart, suspend, shut down) with no
"quit EmulationStation" in it nor in the quick access (SELECT) menu, and the
window can't be closed (Alt+F4) or quit with F4 (retrobox-emulationstation's
patch 0015), and its system settings offer the system's time zone and
keyboard layout (patch 0019, through retrobox.system_settings). Off, as on a
desktop, QUIT only asks whether to quit EmulationStation.

Both come from two settings of es_settings.cfg, which Retrobox writes before
EmulationStation starts: ``ShowOnlyExit`` (QUIT is only a "Really quit?"
question) and ``ShowExit`` (quitting EmulationStation is offered).
"""

from __future__ import annotations

import logging
from pathlib import Path

from retrobox.paths import ES_SETTINGS_CFG, get_ini_value
from retrobox.utils.es_settings import write_es_setting

_logger = logging.getLogger(__name__)

_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})


def console_mode() -> bool:
    """Whether retrobox.ini turns console mode on (``[core] console_mode``)."""
    return get_ini_value("core", "console_mode", "false").lower() in _TRUE_VALUES


def apply_console_mode(settings_path: Path = ES_SETTINGS_CFG) -> bool:
    """Write the quit menu and quitting of console mode (on or off) into es_settings.cfg.

    EmulationStation must not be running: it rewrites the file when it exits.

    Returns:
        True if the file changed.
    """
    on = console_mode()
    value = "false" if on else "true"
    changed = write_es_setting(settings_path, "bool", "ShowOnlyExit", value)
    changed = write_es_setting(settings_path, "bool", "ShowExit", value) or changed
    if changed:
        _logger.info("Console mode %s", "on: EmulationStation can't be quit" if on else "off")
    return changed
