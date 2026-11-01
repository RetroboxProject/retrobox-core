"""Tell whether the hotkey is being held down while a game starts.

Holding the hotkey when a game is launched asks for its emulator to be
installed again (see ``emulator_setup``). "The hotkey" is the hotkey button
of any player's controller, as mapped in EmulationStation (``select`` when
the mapping has no hotkey), or either Shift key of any keyboard, the
keyboard's hotkey in Retrobox. Nothing needs a window with the focus, so it
works the same under any compositor, X11 or none:

* controllers are read through SDL, like EmulationStation reads them, so the
  button numbers of es_input.cfg are the ones SDL reports (the desktop
  EmulationStation doesn't store evdev codes in es_input.cfg);
* keyboards are read from their evdev nodes (``EVIOCGKEY``), which takes
  membership of the "input" group; the installers grant it.

``RETROBOX_REINSTALL_EMULATOR=1`` in the environment has the same effect.
"""

from __future__ import annotations

import ctypes
import logging
import os
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from retrobox.configgen.controller import Controllers

_logger = logging.getLogger(__name__)

_FORCE_VARIABLE: Final = "RETROBOX_REINSTALL_EMULATOR"

# SDL backends that learn a controller's state from its reports (HIDAPI) need
# a moment after opening it; the evdev one reads the current state on open
_SETTLE_SECONDS: Final = 0.15
_POLL_SECONDS: Final = 0.01


def _pad_hotkeys(controllers: Controllers) -> dict[str, set[int]]:
    """SDL button number of each controller's hotkey, by lowercase GUID."""
    wanted: dict[str, set[int]] = defaultdict(set)
    for controller in controllers:
        button = controller.inputs.get("hotkey") or controller.inputs.get("select")
        if button is None or button.type != "button" or not controller.guid:
            continue
        try:
            wanted[controller.guid.lower()].add(int(button.id))
        except ValueError:
            continue
    return wanted


def _open_joysticks(sdl2, wanted: dict[str, set[int]]) -> list[tuple[object, set[int]]]:
    """Open the joysticks whose GUID has a hotkey to watch."""
    opened = []
    for index in range(sdl2.SDL_NumJoysticks()):
        joystick = sdl2.SDL_JoystickOpen(index)
        if not joystick:
            continue
        buffer = ctypes.create_string_buffer(33)
        sdl2.SDL_JoystickGetGUIDString(sdl2.SDL_JoystickGetGUID(joystick), buffer, 33)
        buttons = wanted.get(buffer.value.decode().lower())
        if buttons:
            opened.append((joystick, buttons))
        else:
            sdl2.SDL_JoystickClose(joystick)
    return opened


def _pad_hotkey_held(controllers: Controllers) -> bool:
    wanted = _pad_hotkeys(controllers)
    if not wanted:
        return False
    try:
        import sdl2  # pylint: disable=import-outside-toplevel
    except ImportError:
        _logger.debug("pysdl2 is not available: cannot read the controllers' hotkey")
        return False

    if not sdl2.SDL_WasInit(sdl2.SDL_INIT_JOYSTICK):
        sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"1")
        if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_JOYSTICK):
            _logger.debug("SDL joystick init failed: %s", sdl2.SDL_GetError())
            return False
    opened = _open_joysticks(sdl2, wanted)
    try:
        deadline = time.monotonic() + _SETTLE_SECONDS
        while opened:
            sdl2.SDL_JoystickUpdate()
            for joystick, buttons in opened:
                count = sdl2.SDL_JoystickNumButtons(joystick)
                held = [b for b in buttons if b < count and sdl2.SDL_JoystickGetButton(joystick, b)]
                if held:
                    name = (sdl2.SDL_JoystickName(joystick) or b"").decode(errors="replace")
                    _logger.info("hotkey held on %s (button %s)", name, held[0])
                    return True
            if time.monotonic() >= deadline:
                break
            time.sleep(_POLL_SECONDS)
    finally:
        for joystick, _buttons in opened:
            sdl2.SDL_JoystickClose(joystick)
    return False


def _shift_held() -> bool:
    """Either Shift key down on any readable keyboard."""
    try:
        import evdev  # pylint: disable=import-outside-toplevel
    except ImportError:
        _logger.debug("python evdev is not available: cannot read the keyboards")
        return False
    shifts = {evdev.ecodes.KEY_LEFTSHIFT, evdev.ecodes.KEY_RIGHTSHIFT}
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue  # no permission, or unplugged meanwhile
        try:
            if not shifts.intersection(device.capabilities().get(evdev.ecodes.EV_KEY, [])):
                continue  # not a keyboard
            if shifts.intersection(device.active_keys()):
                _logger.info("Shift held on %s (%s)", device.name, path)
                return True
        except OSError:
            continue
        finally:
            device.close()
    return False


def hotkey_held(controllers: Controllers) -> bool:
    """True when a controller's hotkey or a keyboard's Shift is down (or the variable is set).

    Args:
        controllers: The players' controllers, with their es_input.cfg mapping.
    """
    if os.environ.get(_FORCE_VARIABLE, "") not in ("", "0"):
        _logger.info("%s is set: treating the hotkey as held", _FORCE_VARIABLE)
        return True
    return _shift_held() or _pad_hotkey_held(controllers)
