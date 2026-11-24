"""Controller mapping of Mupen64Plus: the Input-SDL-Control sections of mupen64plus.cfg."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from .mupen64plus_config import quote, set_value

if TYPE_CHECKING:
    from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser

    from ...config import SystemConfig
    from ...controller import Controllers

MAX_PLAYERS: Final = 4

_DEFAULT_LAYOUT: Final = "retropad"
_DEFAULT_SENSITIVITY: Final = 1.0
_MIN_SENSITIVITY: Final = 0.1
_DEFAULT_DEADZONE: Final = 0.01
# the range of the axes of SDL, which the deadzone and the peak of Mupen64Plus are given in
_ANALOG_RANGE: Final = 32768
# the pak plugged in the controller: 1 is none, 2 the memory pak and 3 the rumble pak
_PLUGIN_MEMORY_PAK: Final = 2

# input of the pad for each button of the N64, in each layout: the retropad one is the
# one of RetroArch's Mupen64Plus-Next (B and Y are the A and B of the N64), the n64 one
# is for the pads that have the buttons of the N64 (A and B of Nintendo: east and south)
_BUTTONS: Final = {
    "retropad": {
        "A Button": "b",
        "B Button": "y",
        "Z Trig": "l2",
        "L Trig": "pageup",
        "R Trig": "pagedown",
        "Start": "start",
    },
    "n64": {
        "A Button": "a",
        "B Button": "b",
        "Z Trig": "l2",
        "L Trig": "pageup",
        "R Trig": "pagedown",
        "Start": "start",
    },
}

_DPAD: Final = {"DPad U": "up", "DPad D": "down", "DPad L": "left", "DPad R": "right"}
_HAT_DIRECTIONS: Final = {"up": "Up", "down": "Down", "left": "Left", "right": "Right"}

# the C buttons are the right stick: (button, input of the pad, whether the button is
# the direction of that input or the opposite one)
_C_BUTTONS: Final = (
    ("C Button U", "joystick2up", True),
    ("C Button D", "joystick2up", False),
    ("C Button L", "joystick2left", True),
    ("C Button R", "joystick2left", False),
)

# the analog stick: (axis of the N64, input of the pad that moves it up or left)
_STICK: Final = (("X Axis", "joystick1left"), ("Y Axis", "joystick1up"))


def _negative(pad_input: Any) -> bool:
    """Tell whether the input is moved in the negative direction of its axis."""
    return str(pad_input.value).startswith("-")


def _binding(pad_input: Any, direction: str = "") -> str:
    """Return a button, the direction of a hat or half of an axis as Mupen64Plus names it."""
    if pad_input.type == "button":
        return f"button({pad_input.id})"
    if pad_input.type == "hat" and direction in _HAT_DIRECTIONS:
        return f"hat({pad_input.id} {_HAT_DIRECTIONS[direction]})"
    if pad_input.type == "axis":
        return f"axis({pad_input.id}{'-' if _negative(pad_input) else '+'})"
    return ""


def _half_axis(pad_input: Any, same_direction: bool) -> str:
    """Return half of an axis: the direction of the input, or the opposite one."""
    if pad_input.type != "axis":
        return ""
    sign = "-" if _negative(pad_input) == same_direction else "+"
    return f"axis({pad_input.id}{sign})"


def _stick(pad_input: Any) -> str:
    """Return both directions of an axis, the one of the input first."""
    if pad_input.type != "axis":
        return ""
    low, high = f"{pad_input.id}-", f"{pad_input.id}+"
    first, second = (low, high) if _negative(pad_input) else (high, low)
    return f"axis({first},{second})"


def _number(value: str, default: float) -> float:
    """Return ``value`` as a number, or ``default`` if it is not one."""
    try:
        return float(value)
    except ValueError:
        return default


def _option(config: SystemConfig, name: str, player: int, default: float) -> float:
    """Return a numeric option of one player (``mupen64-deadzone2``...)."""
    return _number(config.get_str(f"{name}{player}", str(default)), default)


def _pad_settings(
    controller: Any, layout: str, sensitivity: float, deadzone: float
) -> dict[str, str]:
    """Return the keys of the Input-SDL-Control section of one controller."""
    inputs = controller.inputs
    dead = round(deadzone * _ANALOG_RANGE)
    # the stick is at full range when it gets to the peak: a lower one is more sensitive
    peak = round(_ANALOG_RANGE / sensitivity)
    settings = {
        "version": "2.000000",
        "mode": "0",
        "device": str(controller.index),
        "name": quote(getattr(controller, "real_name", controller.name)),
        "plugged": "True",
        "plugin": str(_PLUGIN_MEMORY_PAK),
        "mouse": "False",
        "AnalogDeadzone": quote(f"{dead},{dead}"),
        "AnalogPeak": quote(f"{peak},{peak}"),
    }
    for button, name in _BUTTONS[layout].items():
        binding = _binding(inputs[name]) if name in inputs else ""
        settings[button] = quote(binding)
    for button, name in _DPAD.items():
        binding = _binding(inputs[name], name) if name in inputs else ""
        settings[button] = quote(binding)
    for button, name, same_direction in _C_BUTTONS:
        binding = _half_axis(inputs[name], same_direction) if name in inputs else ""
        settings[button] = quote(binding)
    for axis, name in _STICK:
        binding = _stick(inputs[name]) if name in inputs else ""
        settings[axis] = quote(binding)
    return settings


def write_controllers(
    ini: CaseSensitiveConfigParser, config: SystemConfig, players_controllers: Controllers
) -> None:
    """Write the Input-SDL-Control section of each of the four players.

    Args:
        ini: The settings Mupen64Plus left in its file.
        config: The configuration of the game: layout, sensitivity and deadzone of each pad.
        players_controllers: The controllers, with their player number.
    """
    pads = {controller.player_number: controller for controller in players_controllers}
    for player in range(1, MAX_PLAYERS + 1):
        section = f"Input-SDL-Control{player}"
        controller = pads.get(player)
        if controller is None:
            set_value(ini, section, "plugged", False)
            continue
        layout = config.get_str(f"mupen64-controller{player}", _DEFAULT_LAYOUT)
        if layout not in _BUTTONS:
            layout = _DEFAULT_LAYOUT
        sensitivity = _option(config, "mupen64-sensitivity", player, _DEFAULT_SENSITIVITY)
        deadzone = _option(config, "mupen64-deadzone", player, _DEFAULT_DEADZONE)
        settings = _pad_settings(
            controller,
            layout,
            max(sensitivity, _MIN_SENSITIVITY),
            min(max(deadzone, 0.0), 1.0),
        )
        for key, value in settings.items():
            set_value(ini, section, key, value)
