"""Tell whether Shift is being held down while a game starts.

Holding Shift when a game is launched asks for its emulator to be installed
again (see ``emulator_setup``). The state is read straight from the
keyboards' evdev nodes (``EVIOCGKEY``), so it works the same under any
compositor, X11 or none, and doesn't need a window with the focus. Reading
them takes membership of the "input" group, which the installers grant;
without it no keyboard can be opened and Shift is never seen as held.

``RETROBOX_REINSTALL_EMULATOR=1`` in the environment has the same effect, for
setups with no readable keyboard.
"""

from __future__ import annotations

import logging
import os
from typing import Final

_logger = logging.getLogger(__name__)

_FORCE_VARIABLE: Final = "RETROBOX_REINSTALL_EMULATOR"


def shift_held() -> bool:
    """True when either Shift key of any keyboard is down, or the variable is set."""
    if os.environ.get(_FORCE_VARIABLE, "") not in ("", "0"):
        _logger.info("%s is set: treating Shift as held", _FORCE_VARIABLE)
        return True
    try:
        import evdev  # pylint: disable=import-outside-toplevel
    except ImportError:
        _logger.debug("python evdev is not available: cannot read the Shift key")
        return False

    shifts = {evdev.ecodes.KEY_LEFTSHIFT, evdev.ecodes.KEY_RIGHTSHIFT}
    readable = 0
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue  # no permission, or unplugged meanwhile
        try:
            keys = device.capabilities().get(evdev.ecodes.EV_KEY, [])
            if not shifts.intersection(keys):
                continue  # not a keyboard
            readable += 1
            if shifts.intersection(device.active_keys()):
                _logger.info("Shift is held on %s (%s)", device.name, path)
                return True
        except OSError:
            continue
        finally:
            device.close()
    if not readable:
        _logger.debug("no readable keyboard (is the user in the 'input' group?)")
    return False
