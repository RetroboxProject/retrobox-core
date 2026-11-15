"""Standard hotkeys: the actions, how an emulator performs them, and which combination fires them.

Three pieces, kept apart so that each changes on its own:

* ``HotkeyAction``: the closed list of actions a hotkey can ask for;
* the table (``share/pad2key/hotkeys.yaml``, or the user's copy): which
  controller combination (``pad``) or key chord (``keyboard``) asks for
  which action, the same for every emulator;
* the bindings: how one emulator performs each action. Every generator gets
  ``common_bindings()`` and adds or replaces its own with
  ``Generator.hotkey_bindings()``.

A binding is one of:

* ``Keys``: a key chord the emulator listens to, pressed by gamepadly's
  virtual keyboard;
* ``Exec``: a command, run by gamepadly;
* ``Native``: the emulator reads the combination from the controller itself
  (its generator writes it to the emulator's configuration), so gamepadly
  must not fire it too;
* ``None``: the emulator cannot do it; the combination is left free.
"""

from __future__ import annotations

import enum
import logging
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from retrobox.paths import BIN_DIR, HOTKEYS_TABLE, USER_HOTKEYS_TABLE, layered_file
from retrobox.utils.features_yaml import load_feature_yaml

if TYPE_CHECKING:
    from retrobox.configgen.Emulator import Emulator

_logger = logging.getLogger(__name__)

class HotkeyAction(enum.StrEnum):
    """What a hotkey can ask for.

    ``OVERLAY`` opens retrobox-overlay (Hotkey+B); every emulator gets it from
    ``common_bindings`` when the overlay is installed and turned on. The overlay's
    daemon also opens it by itself when a dedicated hotkey is held.

    ``OSK`` opens retrobox-overlay's on-screen keyboard; only emulators whose
    feature file lists ``osk`` bind it (see ``osk_enabled``).
    """

    OVERLAY = "overlay"
    OSK = "osk"
    EXIT = "exit"
    MENU = "menu"
    PAUSE = "pause"
    RESET = "reset"
    SAVE_STATE = "save_state"
    LOAD_STATE = "load_state"
    SLOT_PREV = "slot_prev"
    SLOT_NEXT = "slot_next"
    REWIND = "rewind"
    FAST_FORWARD = "fast_forward"
    SCREENSHOT = "screenshot"
    TRANSLATE = "translate"
    SWAP_SCREENS = "swap_screens"
    NEXT_LAYOUT = "next_layout"
    DISK_NEXT = "disk_next"
    DISK_PREV = "disk_prev"
    DISK_EJECT = "disk_eject"
    TOGGLE_BEZEL = "toggle_bezel"


@dataclass(frozen=True)
class Keys:
    """A key chord (evdev names, e.g. ``("KEY_LEFTSHIFT", "KEY_F3")``)."""

    codes: tuple[str, ...]


@dataclass(frozen=True)
class Exec:
    """A command line (argv, no shell)."""

    argv: tuple[str, ...]


@dataclass(frozen=True)
class Native:
    """The emulator handles the combination itself.

    ``keys`` is the emulator's keyboard shortcut for the same action, when
    it has one: gamepadly ignores it, the overlay presses it.
    """

    keys: tuple[str, ...] = ()


CLOSE_WINDOW = Keys(("KEY_LEFTALT", "KEY_F4"))
"""Alt+F4: emulators that quit cleanly when their window is closed."""

type Binding = Keys | Exec | Native
type Bindings = Mapping[HotkeyAction, Binding | None]


@dataclass(frozen=True)
class HotkeyEntry:
    """One line of the table: a combination and the action it asks for."""

    action: HotkeyAction
    trigger: tuple[str, ...]
    tap: bool = False


# Key names as emulators spell them -> evdev key names
_KEY_ALIASES: dict[str, str] = {
    "shift": "KEY_LEFTSHIFT",
    "ctrl": "KEY_LEFTCTRL",
    "control": "KEY_LEFTCTRL",
    "alt": "KEY_LEFTALT",
    "esc": "KEY_ESC",
    "escape": "KEY_ESC",
    "return": "KEY_ENTER",
    "enter": "KEY_ENTER",
    "space": "KEY_SPACE",
    "tab": "KEY_TAB",
    "backspace": "KEY_BACKSPACE",
    "period": "KEY_DOT",
    "plus": "KEY_EQUAL",
    "minus": "KEY_MINUS",
    "insert": "KEY_INSERT",
}


def evdev_key(name: str) -> str:
    """The evdev name of a key as emulators spell it (``Shift``, ``F5``, ``Escape``, ``O``)."""
    clean = name.strip().strip("`")
    alias = _KEY_ALIASES.get(clean.lower())
    if alias is not None:
        return alias
    if len(clean) >= 2 and clean[0] in "fF" and clean[1:].isdigit():
        return f"KEY_F{int(clean[1:])}"
    if len(clean) == 1 and clean.isalnum():
        return f"KEY_{clean.upper()}"
    raise ValueError(f"unknown key name {name!r}")


def keys_of(names: list[str]) -> Keys:
    """A chord from key names as emulators spell them."""
    return Keys(tuple(evdev_key(name) for name in names))


def common_bindings(system: Emulator | None = None) -> dict[HotkeyAction, Binding | None]:
    """What every emulator gets: leaving the game, screenshots and the overlay.

    The overlay only when it is installed and the ``overlay`` setting (global, per
    system or per game, on by default) is not off; without it Hotkey+B stays free.
    """
    bindings: dict[HotkeyAction, Binding | None] = {
        HotkeyAction.EXIT: Exec((str(BIN_DIR / "retrobox-emukill"),)),
        HotkeyAction.SCREENSHOT: Exec((str(BIN_DIR / "retrobox-screenshot"),)),
    }
    if shutil.which(OVERLAY_COMMAND) is not None and (
        system is None or overlay_enabled(system)
    ):
        bindings[HotkeyAction.OVERLAY] = Exec((OVERLAY_COMMAND,))
    if system is not None and osk_enabled(system):
        bindings[HotkeyAction.OSK] = Exec((OVERLAY_COMMAND, "--osk"))
    return bindings


UNIVERSAL_ACTIONS: frozenset[HotkeyAction] = frozenset(
    {HotkeyAction.EXIT, HotkeyAction.OVERLAY, HotkeyAction.SCREENSHOT, HotkeyAction.OSK}
)
"""The commands that mean the same everywhere: they take their combination from
a gamepad profile that maps it to something else (an app's Alt+F4, say)."""

OVERLAY_COMMAND = "retrobox-overlay"
"""The overlay's command, found through ``PATH``."""

OSK_FEATURE = "osk"
"""The feature that lists an emulator's feature file as one the on-screen keyboard works with."""


def _has_osk_feature(emulator: str) -> bool:
    """Whether the emulator's feature file (``emulator_options/<emulator>.yaml``) lists ``osk``."""
    path = layered_file(f"emulator_options/{emulator}.yaml")
    if path is None:
        return False
    try:
        with path.open(encoding="utf-8") as file:
            data = load_feature_yaml(file)
    except (OSError, yaml.YAMLError) as err:
        # best effort: a broken feature file must never prevent the game from starting
        _logger.warning("cannot read the features of %s: %s", emulator, err)
        return False
    features = data.get("features") if isinstance(data, dict) else None
    return isinstance(features, list) and OSK_FEATURE in features


def osk_enabled(system: Emulator) -> bool:
    """Whether the on-screen keyboard may open over this game.

    The emulator's feature file must list ``osk``, and the ``osk`` setting
    (global, per system or per game, on by default) must not turn it off;
    published in session.json.
    """
    return _has_osk_feature(system.config.emulator) and system.config.get_bool(OSK_FEATURE, True)


def overlay_enabled(system: Emulator) -> bool:
    """Whether the overlay may open over this game (``overlay``: global, per
    system or per game, on by default); published in session.json."""
    return system.config.get_bool("overlay", True)


def _parse_entry(raw: Any, index: int, source: Path) -> HotkeyEntry | None:
    """Check one table line; None (and a warning) when it is invalid."""
    error = None
    entry = None
    if not isinstance(raw, dict):
        error = "not a mapping"
    else:
        trigger = raw.get("trigger")
        tap = bool(raw.get("tap", False))
        if isinstance(trigger, str):
            trigger = [trigger]
        try:
            action = HotkeyAction(raw.get("action"))
        except ValueError:
            error = f"unknown action {raw.get('action')!r}"
        else:
            if not trigger or not all(isinstance(name, str) for name in trigger):
                error = "'trigger' must be a list of input names"
            elif tap and len(trigger) != 1:
                error = "'tap' needs a single input"
            else:
                entry = HotkeyEntry(action=action, trigger=tuple(trigger), tap=tap)
    if error is not None:
        _logger.warning("%s, hotkey #%d: %s: ignored", source, index, error)
    return entry


PAD_SECTION = "pad"
KEYBOARD_SECTION = "keyboard"


def _read_table(path: Path, section: str) -> list[HotkeyEntry] | None:
    """The entries of one section of a table file; None when it is missing or unreadable."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, yaml.YAMLError) as err:
        _logger.warning("cannot read the hotkeys table %s: %s", path, err)
        return None
    if not isinstance(data, dict):
        _logger.warning("%s: a mapping is expected", path)
        return None
    if section not in data:
        return None
    if not isinstance(data[section], list):
        _logger.warning("%s: '%s' must be a list", path, section)
        return None
    entries = (_parse_entry(raw, index, path) for index, raw in enumerate(data[section]))
    valid = [entry for entry in entries if entry is not None]
    if section == KEYBOARD_SECTION:
        valid = [entry for entry in valid if _keyboard_trigger_ok(entry, path)]
    return valid


def _keyboard_trigger_ok(entry: HotkeyEntry, source: Path) -> bool:
    """Keyboard triggers are evdev key names (``KEY_LEFTSHIFT``, ``KEY_ESC``...)."""
    if all(name.startswith("KEY_") for name in entry.trigger):
        return True
    _logger.warning("%s: keyboard hotkey %r: evdev key names expected: ignored",
                    source, entry.trigger)
    return False


def load_table(
    section: str = PAD_SECTION,
    user_table: Path = USER_HOTKEYS_TABLE,
    default_table: Path = HOTKEYS_TABLE,
) -> list[HotkeyEntry]:
    """One section of the hotkeys table (``pad`` or ``keyboard``).

    The user's table wins when it has the section (and is readable); the
    shipped one gives the sections it lacks.
    """
    for path in (user_table, default_table):
        entries = _read_table(path, section)
        if entries is not None:
            _logger.debug("hotkeys table, %s: %s", section, path)
            return entries
    return []


def pad_buttons(table: list[HotkeyEntry], action: HotkeyAction) -> list[tuple[str, ...]]:
    """The combinations the table gives an action (taps excluded)."""
    return [entry.trigger for entry in table if entry.action is action and not entry.tap]
