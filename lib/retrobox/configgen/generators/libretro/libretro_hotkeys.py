"""RetroArch and the standard hotkeys.

RetroArch reads "hotkey + button" combinations from the controller itself
(``input_enable_hotkey_btn`` plus one ``input_<action>_btn`` per action), so
the combinations of the standard table that have that shape are written to
its configuration and bound as ``Native``: gamepadly leaves them alone and
RetroArch performs them (and quits cleanly on Hotkey+Start). Combinations of
another shape fall back to RetroArch's keyboard hotkeys (Shift + key), which
gamepadly presses. Screenshots and the overlay are Retrobox's own
(``hotkeys.common_bindings``), not RetroArch's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

from retrobox.configgen.hotkeys import HotkeyAction, Keys, Native

if TYPE_CHECKING:
    from retrobox.configgen.hotkeys import Binding, HotkeyEntry

HOTKEY_INPUT: Final = "hotkey"


class RetroArchAction(NamedTuple):
    """A RetroArch input bind and its keyboard hotkey (pressed with Shift)."""

    setting: str
    key: str | None


# The keyboard keys match the ones libretroControllers writes for Shift.
ACTIONS: Final[dict[HotkeyAction, RetroArchAction]] = {
    HotkeyAction.EXIT: RetroArchAction("input_exit_emulator", "KEY_ESC"),
    HotkeyAction.MENU: RetroArchAction("input_menu_toggle", "KEY_F1"),
    HotkeyAction.PAUSE: RetroArchAction("input_pause_toggle", "KEY_P"),
    HotkeyAction.SAVE_STATE: RetroArchAction("input_save_state", "KEY_F3"),
    HotkeyAction.LOAD_STATE: RetroArchAction("input_load_state", "KEY_F4"),
    HotkeyAction.SLOT_PREV: RetroArchAction("input_state_slot_decrease", "KEY_F5"),
    HotkeyAction.SLOT_NEXT: RetroArchAction("input_state_slot_increase", "KEY_F6"),
    HotkeyAction.TRANSLATE: RetroArchAction("input_ai_service", "KEY_F9"),
    HotkeyAction.RESET: RetroArchAction("input_reset", "KEY_F10"),
    HotkeyAction.REWIND: RetroArchAction("input_rewind", "KEY_F11"),
    HotkeyAction.FAST_FORWARD: RetroArchAction("input_hold_fast_forward", "KEY_F12"),
    HotkeyAction.DISK_NEXT: RetroArchAction("input_disk_next", None),
    HotkeyAction.DISK_PREV: RetroArchAction("input_disk_prev", None),
    HotkeyAction.DISK_EJECT: RetroArchAction("input_disk_eject_toggle", None),
}


def native_buttons(table: list[HotkeyEntry]) -> dict[HotkeyAction, str]:
    """The button RetroArch pairs with the hotkey for each action it can read itself.

    Only "hotkey + one button" combinations (not taps) qualify; the first one
    in the table wins for an action, and a button is given to one action only.
    """
    buttons: dict[HotkeyAction, str] = {}
    used: set[str] = set()
    for entry in table:
        if entry.tap or entry.action not in ACTIONS or entry.action in buttons:
            continue
        if len(entry.trigger) != 2 or entry.trigger[0] != HOTKEY_INPUT:
            continue
        button = entry.trigger[1]
        if button == HOTKEY_INPUT or button in used:
            continue
        buttons[entry.action] = button
        used.add(button)
    return buttons


def pad_hotkey_settings(table: list[HotkeyEntry]) -> dict[str, str]:
    """ES input name -> RetroArch setting, for the combinations RetroArch reads itself."""
    return {button: ACTIONS[action].setting for action, button in native_buttons(table).items()}


def bindings(table: list[HotkeyEntry]) -> dict[HotkeyAction, Binding | None]:
    """How RetroArch performs each action of the table."""
    native = native_buttons(table)
    result: dict[HotkeyAction, Binding | None] = {}
    for action, retroarch in ACTIONS.items():
        keys = ("KEY_LEFTSHIFT", retroarch.key) if retroarch.key is not None else ()
        if action in native:
            result[action] = Native(keys)
        elif keys:
            result[action] = Keys(keys)
        else:
            result[action] = None
    # RetroArch cannot swap screens, change the layout or toggle the bezel
    for action in (HotkeyAction.SWAP_SCREENS, HotkeyAction.NEXT_LAYOUT,
                   HotkeyAction.TOGGLE_BEZEL):
        result[action] = None
    return result
