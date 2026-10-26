"""Controller mapping of Ares: the VirtualPad sections of settings.bml."""

from __future__ import annotations

from typing import Any

# ids of the groups of a joypad in Ares
_GROUP_AXIS = 0
_GROUP_HAT = 1
_GROUP_BUTTON = 3

_MAX_PADS = 5

# (label in the bml, internal name, optional target direction)
_GAMEPAD_MAPPING: list[tuple[str, str, str | None]] = [
    ("Pad.Up", "up", None),
    ("Pad.Down", "down", None),
    ("Pad.Left", "left", None),
    ("Pad.Right", "right", None),
    ("Select", "select", None),
    ("Start", "start", None),
    ("A..South", "b", None),
    ("B..East", "a", None),
    ("X..West", "y", None),
    ("Y..North", "x", None),
    ("L-Bumper", "pageup", None),
    ("R-Bumper", "pagedown", None),
    ("L-Trigger", "l2", "/Hi"),
    ("R-Trigger", "r2", "/Hi"),
    ("L-Stick..Click", "l3", None),
    ("R-Stick..Click", "r3", None),
    ("L-Up", "joystick1up", "/Lo"),
    ("L-Down", "joystick1up", "/Hi"),
    ("L-Left", "joystick1left", "/Lo"),
    ("L-Right", "joystick1left", "/Hi"),
    ("R-Up", "joystick2up", "/Lo"),
    ("R-Down", "joystick2up", "/Hi"),
    ("R-Left", "joystick2left", "/Lo"),
    ("R-Right", "joystick2left", "/Hi"),
]


def _compute_guid_indices(players_controllers: Any) -> dict[int, int]:
    """Return, for each controller, its position among the pads that share its GUID.

    It uses the real SDL index that EmulationStation gave to each player
    (``controller.index``) and not the position P1..P5. It is the same problem,
    with the same solution, as in libretroControllers.py, edenGenerator.py and
    ryujinxGenerator.py.
    """
    guid_indices: dict[int, int] = {}
    seen: dict[str, int] = {}
    for controller in sorted(players_controllers, key=lambda pad: pad.index):
        position = seen.get(controller.guid, 0)
        guid_indices[id(controller)] = position
        seen[controller.guid] = position + 1
    return guid_indices


def _ares_get_ctrler_entry(
    name: str,
    guid: str,
    guid_index: int,
    inputs: Any,
    target_dir: str | None = None,
) -> str:
    """Translate a logical input (like 'up' or 'l2') to the binding format of Ares.

    The format is ``guid/slot/group/input[/direction]``. It returns an empty
    string when the pad does not map that input.
    """
    if name not in inputs:
        return ""

    pad_input = inputs[name]
    input_type = getattr(pad_input, "type", None)
    input_id = getattr(pad_input, "id", "0")
    input_value = str(getattr(pad_input, "value", "1"))

    if input_type == "button":
        return f"{guid}/{guid_index}/{_GROUP_BUTTON}/{input_id}"
    if input_type == "hat":
        hat_id = "1" if name in ("up", "down") else "0"
        direction = "/Lo" if name in ("up", "left") else "/Hi"
        return f"{guid}/{guid_index}/{_GROUP_HAT}/{hat_id}{direction}"
    if input_type == "axis":
        direction = target_dir or (
            "/Hi" if input_value.startswith("-") or int(float(input_value)) > 0 else "/Lo"
        )
        return f"{guid}/{guid_index}/{_GROUP_AXIS}/{input_id}{direction}"
    return ""


def _ares_rumble_entry(guid: str, guid_index: int) -> str:
    """Return the binding that sends the rumble of the game to this pad.

    Only the device of a rumble binding matters, because Ares drives the whole
    motor of the pad through it, so no button of the pad is needed.
    """
    return f"{guid}/{guid_index}/{_GROUP_BUTTON}/0/Rumble"


def _ares_gen_gamepad_conf(pad_num: int, guid: str, guid_index: int, inputs: Any) -> str:
    """Return the full VirtualPadN block of one controller."""
    lines = [f"VirtualPad{pad_num}"]
    for label, name, target_dir in _GAMEPAD_MAPPING:
        entry = _ares_get_ctrler_entry(name, guid, guid_index, inputs, target_dir)
        lines.append(f"  {label}: {entry};;")
    lines.append(f"  Rumble: {_ares_rumble_entry(guid, guid_index)};;")
    return "\n".join(lines) + "\n"


def _ares_create_pads_config(players_controllers: Any) -> str:
    """Return the mapping of up to five controllers for the settings.bml of Ares."""
    guid_indices = _compute_guid_indices(players_controllers)

    pads_config = ""
    for index, controller in enumerate(players_controllers):
        if index >= _MAX_PADS:
            break
        guid_index = guid_indices[id(controller)]
        pads_config += _ares_gen_gamepad_conf(
            index + 1, controller.guid, guid_index, controller.inputs
        )
    return pads_config
