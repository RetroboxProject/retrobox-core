"""Gamepad input of the setup screen: player 1 as EmulationStation maps it.

The launcher hands over player 1's mapping from es_input.cfg (``--pad-map
name=type:id:value``). EmulationStation reads joysticks through SDL too, so
the button, hat and axis numbers are the ones SDL reports here. Without a
mapping (the launcher was not given one), any game controller is accepted with
SDL's standard layout, confirm being the east button: SNES "A".
"""

from __future__ import annotations

import ctypes
import enum
from typing import TYPE_CHECKING, NamedTuple

import sdl2

if TYPE_CHECKING:
    from collections.abc import Iterable

_AXIS_THRESHOLD = 16000


class Action(enum.Enum):
    """What the screen understands, whatever the device."""

    CONFIRM = enum.auto()
    BACK = enum.auto()
    LEFT = enum.auto()
    RIGHT = enum.auto()
    UP = enum.auto()
    DOWN = enum.auto()


# es_input.cfg input name -> action (the stick names are their negative side)
_ES_ACTIONS = {
    "a": Action.CONFIRM,
    "b": Action.BACK,
    "left": Action.LEFT,
    "right": Action.RIGHT,
    "up": Action.UP,
    "down": Action.DOWN,
    "joystick1left": Action.LEFT,
    "joystick1up": Action.UP,
}
# the positive side of the stick inputs
_OPPOSITE = {Action.LEFT: Action.RIGHT, Action.UP: Action.DOWN}

_CONTROLLER_ACTIONS = {
    sdl2.SDL_CONTROLLER_BUTTON_B: Action.CONFIRM,  # east: SNES A
    sdl2.SDL_CONTROLLER_BUTTON_A: Action.BACK,  # south: SNES B
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT: Action.LEFT,
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT: Action.RIGHT,
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP: Action.UP,
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN: Action.DOWN,
}


class _Binding(NamedTuple):
    kind: str  # "button", "hat" or "axis"
    index: int
    value: int
    action: Action


def parse_mapping(specs: Iterable[str]) -> list[_Binding]:
    """Turn ``name=type:id:value`` strings into bindings, skipping unknown ones."""
    bindings: list[_Binding] = []
    for spec in specs:
        name, _, rest = spec.partition("=")
        parts = rest.split(":")
        action = _ES_ACTIONS.get(name)
        if action is None or len(parts) != 3 or parts[0] not in ("button", "hat", "axis"):
            continue
        try:
            index, value = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if parts[0] == "axis" and name.startswith("joystick"):
            # one entry covers both directions of the stick axis
            bindings.append(_Binding("axis", index, value, action))
            bindings.append(_Binding("axis", index, -value, _OPPOSITE[action]))
        else:
            bindings.append(_Binding(parts[0], index, value, action))
    return bindings


def _guid_of(device_index: int) -> str:
    buffer = ctypes.create_string_buffer(33)
    sdl2.SDL_JoystickGetGUIDString(sdl2.SDL_JoystickGetDeviceGUID(device_index), buffer, 33)
    return buffer.value.decode().lower()


def _hardware_id(guid: str) -> str:
    """Vendor and product of an SDL GUID (bus and name CRC can differ by driver)."""
    return guid[8:12] + guid[16:20] if len(guid) == 32 else guid


class PadInput:
    """Turns SDL joystick events into actions."""

    def __init__(self, guid: str | None, device_path: str | None, bindings: list[_Binding]) -> None:
        self._guid = (guid or "").lower()
        self._device_path = device_path or ""
        self._bindings = bindings
        self._player_one: int | None = None  # SDL instance id
        self._joysticks: list = []
        self._controllers: list = []
        self._held: set[tuple[str, int, int]] = set()

    def _is_player_one(self, device_index: int) -> bool:
        if not self._bindings or self._player_one is not None:
            return False
        path_getter = getattr(sdl2, "SDL_JoystickPathForIndex", None)
        if self._device_path and path_getter is not None:
            path = path_getter(device_index)
            if path and path.decode() == self._device_path:
                return True
        guid = _guid_of(device_index)
        if not self._guid:
            return False
        return guid == self._guid or _hardware_id(guid) == _hardware_id(self._guid)

    def device_added(self, device_index: int) -> None:
        """Open a joystick that just appeared (SDL also reports the ones present at start)."""
        if self._is_player_one(device_index):
            joystick = sdl2.SDL_JoystickOpen(device_index)
            if joystick:
                self._joysticks.append(joystick)
                self._player_one = sdl2.SDL_JoystickInstanceID(joystick)
        elif not self._bindings and sdl2.SDL_IsGameController(device_index):
            controller = sdl2.SDL_GameControllerOpen(device_index)
            if controller:
                self._controllers.append(controller)

    def device_removed(self, instance_id: int) -> None:
        """Forget player 1 when it is unplugged (it is matched again if it comes back)."""
        if instance_id == self._player_one:
            self._player_one = None
            self._held.clear()

    def translate(self, event: sdl2.SDL_Event) -> Action | None:
        """The action of an event, on press only (holding does not repeat)."""
        kind = event.type
        if kind == sdl2.SDL_CONTROLLERBUTTONDOWN and not self._bindings:
            return _CONTROLLER_ACTIONS.get(event.cbutton.button)
        if self._player_one is None:
            return None
        if kind == sdl2.SDL_JOYBUTTONDOWN and event.jbutton.which == self._player_one:
            return self._match("button", event.jbutton.button, lambda value: True)
        if kind == sdl2.SDL_JOYHATMOTION and event.jhat.which == self._player_one:
            hat = event.jhat.value
            return self._edge("hat", event.jhat.hat, lambda value: bool(hat & value))
        if kind == sdl2.SDL_JOYAXISMOTION and event.jaxis.which == self._player_one:
            position = event.jaxis.value
            return self._edge(
                "axis", event.jaxis.axis, lambda value: position * value > _AXIS_THRESHOLD
            )
        return None

    def _match(self, kind: str, index: int, active) -> Action | None:
        for binding in self._bindings:
            if binding.kind == kind and binding.index == index and active(binding.value):
                return binding.action
        return None

    def _edge(self, kind: str, index: int, active) -> Action | None:
        """Hats and axes report positions: act when one starts being pressed."""
        result = None
        for binding in self._bindings:
            if binding.kind != kind or binding.index != index:
                continue
            key = (kind, index, binding.value)
            if active(binding.value):
                if key not in self._held:
                    self._held.add(key)
                    result = result or binding.action
            else:
                self._held.discard(key)
        return result

    def close(self) -> None:
        """Close every device opened."""
        for joystick in self._joysticks:
            sdl2.SDL_JoystickClose(joystick)
        for controller in self._controllers:
            sdl2.SDL_GameControllerClose(controller)
        self._joysticks.clear()
        self._controllers.clear()
