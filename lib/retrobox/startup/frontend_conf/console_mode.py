"""Console mode: EmulationStation as a console's only screen, not a program to quit.

On (``retrobox --console``), QUIT in EmulationStation's main menu opens
batocera's full quit menu (restart, suspend, shut down) with no "quit
EmulationStation" in it nor in the quick access (SELECT) menu, and the
window can't be closed (Alt+F4) or quit with F4 (retrobox-emulationstation's
patch 0015). Off, as on a desktop, QUIT only asks whether to quit
EmulationStation.

Both come from two settings of es_settings.cfg, which Retrobox writes before
EmulationStation starts: ``ShowOnlyExit`` (QUIT is only a "Really quit?"
question) and ``ShowExit`` (quitting EmulationStation is offered).

Console mode is turned on only by the ``--console`` argument to ``retrobox``
(see bin/retrobox); there is no setting that turns it on or off.

The machine's own settings (time zone, keyboard layout, language) are not
Retrobox's: a system settings program provided by what turns the machine into a
console (retrobox-system-settings) sets them. In console mode its path goes
into es_settings.cfg (``RetroboxSystemSettings``), and EmulationStation's
system settings then offer them (patches 0019 and 0020); with no such program,
they don't. It is ``[core] system_settings`` in retrobox.ini, else
``retrobox-system-settings`` from the PATH. EmulationStation runs it as::

    <program> timezone get | set ZONE
    <program> keyboard get | list-layouts | list-variants LAYOUT | set LAYOUT [VARIANT]
    <program> locale get | list | set LANGUAGE

``get`` prints the value (``<layout> <variant>`` for the keyboard, ``none``
for no variant; a language is ``es_ES``), lists print ``<code> <description>`` lines, and a failure
exits non-zero with the reason as its last line, which EmulationStation shows.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Final

from retrobox.paths import ES_SETTINGS_CFG, get_ini_value
from retrobox.utils.es_settings import write_es_setting

_logger = logging.getLogger(__name__)

SYSTEM_SETTINGS_PROGRAM: Final = "retrobox-system-settings"
"""The system settings program looked for in the PATH."""


def system_settings_program() -> str:
    """The system settings program, or ``""`` if there is none.

    ``[core] system_settings`` in retrobox.ini (a path, or a name in the PATH),
    else ``retrobox-system-settings`` from the PATH; only an executable file counts.
    """
    configured = get_ini_value("core", "system_settings", "").strip()
    name = os.path.expanduser(configured) if configured else SYSTEM_SETTINGS_PROGRAM
    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())
    if configured:
        _logger.warning("[core] system_settings: %s is not an executable", configured)
    return ""


def apply_console_mode(on: bool, settings_path: Path = ES_SETTINGS_CFG) -> bool:
    """Write console mode (on or off) into es_settings.cfg.

    ``on`` is the ``--console`` argument to ``retrobox``; it is the only way
    to turn console mode on. EmulationStation must not be running: it
    rewrites the file when it exits.

    Returns:
        True if the file changed.
    """
    value = "false" if on else "true"
    changed = write_es_setting(settings_path, "bool", "ShowOnlyExit", value)
    changed = write_es_setting(settings_path, "bool", "ShowExit", value) or changed
    program = system_settings_program() if on else ""
    changed = write_es_setting(settings_path, "string", "RetroboxSystemSettings",
                               program) or changed
    if changed:
        _logger.info("Console mode %s", "on: EmulationStation can't be quit" if on else "off")
        if on:
            _logger.info("System settings: %s", program or f"none (no {SYSTEM_SETTINGS_PROGRAM})")
    return changed
