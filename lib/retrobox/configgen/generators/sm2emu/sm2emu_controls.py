"""Per-game gamepad button layout of sm2-emu.

sm2-emu reads the pads through SDL3 and binds each cabinet control (Button 1-4,
directions, Start, Coin, gears) to an SDL gamepad button, that is a POSITION
(south, east, west, north...). Retrobox gives SDL the EmulationStation mapping
of every pad (SDL_GAMECONTROLLERCONFIG), so the positions already follow it:
the layouts here only choose which control sits on which position, and never
touch the raw buttons of a pad. Wheels are not concerned (see sm2emu_config).

The layouts live in ``configgen/data/sm2emu/button_layouts.yaml`` (taken from
RetroBat) and are written to the ``[gamepad]`` keys of sm2-emu.ini, the layout
of every game. A ``[<family>]`` section the user saved from the overlay of
sm2-emu still replaces it for that game, as sm2-emu does.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

import yaml

from retrobox.paths import SHARE_DIR, layered_file

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ...config import SystemConfig

_logger = logging.getLogger(__name__)

_LAYOUTS_RELPATH: Final = "configgen/data/sm2emu/button_layouts.yaml"

# the values of the sm2_button_layout option
LAYOUT_GAME: Final = "auto"  # the layout of the game, on a gamepad
LAYOUT_EMULATOR: Final = "emulator"  # sm2-emu's own default layout
LAYOUT_KEEP: Final = "custom"  # whatever was set in the overlay of sm2-emu
PANEL_LAYOUTS: Final = ("modern8", "8alternative", "6alternative")

# SDL_GamepadButton of each position; a trigger is 100 + its SDL_GamepadAxis
_SDL_BUTTONS: Final[Mapping[str, int]] = {
    "south": 0,
    "east": 1,
    "west": 2,
    "north": 3,
    "select": 4,
    "start": 6,
    "l3": 7,
    "r3": 8,
    "l1": 9,
    "r1": 10,
    "up": 11,
    "down": 12,
    "left": 13,
    "right": 14,
    "l2": 104,
    "r2": 105,
}

# controls of the YAML file -> sm2-emu pad roles, in sm2-emu's order
_ROLES: Final[Mapping[str, str]] = {
    "button1": "button1",
    "button2": "button2",
    "button3": "button3",
    "button4": "button4",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "start": "start",
    "coin": "coin",
    "gearup": "gear_up",
    "geardown": "gear_down",
}

# sm2-emu's own layout (Config::PadLayout): the d-pad, Start, Back as Coin,
# the shoulders as gears and the face buttons from south to north
_EMULATOR_DEFAULTS: Final[Mapping[str, int]] = {
    "button1": 0,
    "button2": 1,
    "button3": 2,
    "button4": 3,
    "up": 11,
    "down": 12,
    "left": 13,
    "right": 14,
    "start": 6,
    "coin": 4,
    "gear_up": 10,
    "gear_down": 9,
}
# what a game layout starts from: the face buttons only come from the file
_ALWAYS_MAPPED: Final[Mapping[str, int]] = {
    role: button for role, button in _EMULATOR_DEFAULTS.items() if not role.startswith("button")
}

# analogue roles of sm2-emu; -1 keeps its defaults: aim and steering on the
# left stick, accelerator on the right trigger, brake on the left trigger and
# the right lever of Virtual On on the right stick
_AXES: Final = ("aim_x", "aim_y", "accel", "brake", "lever_x", "lever_y")
_PEDALS: Final = ("accel", "brake")
_AIM: Final = ("aim_x", "aim_y")
_UNSET: Final = -1
_PLAYERS: Final = 2


def _load_layouts() -> dict[str, dict[str, str]]:
    """Read the layouts file of the highest configuration layer.

    Returns:
        Every section, as {position: controls}, or nothing when the file is
        missing or broken (sm2-emu then gets the default layout).
    """
    path = layered_file(_LAYOUTS_RELPATH) or SHARE_DIR / _LAYOUTS_RELPATH
    try:
        with path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as error:
        _logger.warning("cannot read the sm2-emu button layouts %s: %s", path, error)
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(name): {str(key).lower(): str(value) for key, value in section.items()}
        for name, section in data.items()
        if isinstance(section, dict)
    }


def _section_names(game_set: str | None, family: str | None, panel: str | None) -> list[str]:
    """Return the sections to look for, most specific first."""
    bases = list(dict.fromkeys(name for name in (game_set, family, "default") if name))
    names = [f"{base}_{panel}" for base in bases] if panel else []
    return names + bases


def _apply_section(roles: dict[str, int], section: Mapping[str, str], name: str) -> None:
    """Bind the controls of a section on top of ``roles``."""
    set_here: set[str] = set()
    for position, controls in section.items():
        if (button := _SDL_BUTTONS.get(position)) is None:
            _logger.warning("sm2-emu layout %s: unknown button position '%s'", name, position)
            continue
        for control in (c.strip() for c in controls.split(",")):
            if not control:
                continue
            if (role := _ROLES.get(control.lower())) is None:
                _logger.warning("sm2-emu layout %s: unknown control '%s'", name, control)
            elif role in set_here:
                _logger.warning(
                    "sm2-emu layout %s: '%s' bound twice, '%s' ignored", name, control, position
                )
            else:
                roles[role] = button
                set_here.add(role)


def game_roles(
    game_set: str | None, family: str | None, panel: str | None = None
) -> dict[str, int]:
    """Return the SDL button of every sm2-emu role for a game.

    Args:
        game_set: The set of the game (``vf2a``), when the archive is named after it.
        family: Its parent set (``vf2``).
        panel: An arcade panel layout, or None for a gamepad.
    """
    roles = dict(_ALWAYS_MAPPED)
    layouts = _load_layouts()
    for name in _section_names(game_set, family, panel):
        if (section := layouts.get(name)) is not None:
            _logger.debug("sm2-emu button layout: %s", name)
            _apply_section(roles, section, name)
            return roles
    # no file: sm2-emu's own face buttons
    return dict(_EMULATOR_DEFAULTS)


def _layout_keys(roles: Mapping[str, int]) -> dict[str, str]:
    """Return the [gamepad] keys of a layout, the same one for both players."""
    keys: dict[str, str] = {}
    for player in range(1, _PLAYERS + 1):
        prefix = f"pad{player}_"
        for role in _EMULATOR_DEFAULTS:
            keys[f"{prefix}button_{role}"] = str(roles.get(role, _UNSET))
        for axis in _AXES:
            keys[f"{prefix}axis_{axis}"] = str(_UNSET)
            if axis in _PEDALS or axis in _AIM:
                keys[f"{prefix}axis_{axis}_invert"] = "false"
            if axis in _PEDALS:
                keys[f"{prefix}axis_{axis}_button"] = str(_UNSET)
    return keys


def layout_settings(
    config: SystemConfig, game_set: str | None, family: str | None
) -> dict[str, str]:
    """Return the [gamepad] layout keys to write for the game.

    The ``sm2_button_layout`` option picks the layout of the game on a gamepad
    (the default), an arcade panel layout, sm2-emu's own one, or none at all to
    keep the layout set in the overlay of sm2-emu.
    """
    choice = config.get_str("sm2_button_layout", LAYOUT_GAME)
    if choice == LAYOUT_KEEP:
        return {}
    if choice == LAYOUT_EMULATOR:
        return _layout_keys(_EMULATOR_DEFAULTS)
    panel = choice if choice in PANEL_LAYOUTS else None
    return _layout_keys(game_roles(game_set, family, panel))
