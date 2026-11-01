"""Tell whether the hotkey is being held down while a game starts.

Holding the hotkey when a game is launched asks for its emulator to be
installed again (see ``emulator_setup``). "The hotkey" is the hotkey button
of any player's controller, as mapped in EmulationStation (``select`` when
the mapping has no hotkey), or either Shift key of any keyboard, the
keyboard's hotkey in Retrobox.

The state is read straight from the evdev nodes (``EVIOCGKEY``), so it works
the same under any compositor, X11 or none, and doesn't need a window with
the focus. The controllers' nodes are readable by the seat user; keyboards
need membership of the "input" group, which the installers grant (without
it, only the controllers are checked).

``RETROBOX_REINSTALL_EMULATOR=1`` in the environment has the same effect.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from retrobox.configgen.controller import Controllers

_logger = logging.getLogger(__name__)

_FORCE_VARIABLE: Final = "RETROBOX_REINSTALL_EMULATOR"


def _pad_hotkeys(controllers: Controllers) -> dict[str, set[int]]:
    """evdev key code of each controller's hotkey, by (resolved) device node."""
    wanted: dict[str, set[int]] = defaultdict(set)
    for controller in controllers:
        button = controller.inputs.get("hotkey") or controller.inputs.get("select")
        if button is None or button.type != "button" or not controller.device_path:
            continue
        try:
            code = int(button.code or "")
        except ValueError:
            continue  # an old es_input.cfg without evdev codes
        wanted[os.path.realpath(controller.device_path)].add(code)
    return wanted


def hotkey_held(controllers: Controllers) -> bool:
    """True when a controller's hotkey or a keyboard's Shift is down (or the variable is set).

    Args:
        controllers: The players' controllers, with their es_input.cfg mapping.
    """
    if os.environ.get(_FORCE_VARIABLE, "") not in ("", "0"):
        _logger.info("%s is set: treating the hotkey as held", _FORCE_VARIABLE)
        return True
    try:
        import evdev  # pylint: disable=import-outside-toplevel
    except ImportError:
        _logger.debug("python evdev is not available: cannot read the hotkey")
        return False

    shifts = {evdev.ecodes.KEY_LEFTSHIFT, evdev.ecodes.KEY_RIGHTSHIFT}
    pad_hotkeys = _pad_hotkeys(controllers)
    for path in evdev.list_devices():
        watched = set(pad_hotkeys.get(os.path.realpath(path), ()))
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue  # no permission, or unplugged meanwhile
        try:
            keys = device.capabilities().get(evdev.ecodes.EV_KEY, [])
            if shifts.intersection(keys):  # a keyboard
                watched |= shifts
            if watched and watched.intersection(device.active_keys()):
                _logger.info("hotkey held on %s (%s)", device.name, path)
                return True
        except OSError:
            continue
        finally:
            device.close()
    return False
