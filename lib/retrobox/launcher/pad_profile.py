"""The pad profile of the game being played: its mappings plus the standard hotkeys.

The overlay's input daemon (``retrobox-inputd``) maps the game's controllers
with it while the game runs: session.json names it (``pad_profile``). Its
format is evmapy's ``.keys`` with gamepadly's additions, which the daemon
reads as gamepadly did.

Two layers, merged into ``<runtime dir>/pad2key/session.keys``:

1. the game's own profile (see find_profile(): per game, system, emulator,
   core; ``share/pad2key/profiles`` and the user's), with the full
   pad-to-keyboard mappings of keyboard-only games;
2. the standard hotkeys (``retrobox.configgen.hotkeys``): the pad ones for
   player 1, as the emulator performs them, and the keyboard ones
   (``actions_keyboard``).

The first layer wins: a combination it already maps is not touched, so a
game or system profile can still do its own thing with any hotkey.

The keyboard chords reach the emulator too, and the user holds their
modifier while the mapper would press its keys, so only commands are bound
to them: an emulator's key binding gives way to the common command for the
action (``retrobox-emukill`` to leave), and a chord the emulator reads
itself (``Native``, or the very same keys) is left to it.
"""

from __future__ import annotations

import json
import logging
import shlex
from typing import TYPE_CHECKING, Any

from retrobox.configgen.hotkeys import (
    KEYBOARD_SECTION,
    Exec,
    HotkeyAction,
    Keys,
    Native,
    UNIVERSAL_ACTIONS,
    common_bindings,
    load_table,
)

from retrobox.paths import _GAMEPADLY_PROFILES, _GAMEPADLY_USER_PROFILES

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from retrobox.configgen.Emulator import Emulator
    from retrobox.configgen.generators.Generator import Generator
    from retrobox.configgen.hotkeys import Binding, HotkeyEntry

_logger = logging.getLogger(__name__)

_HOTKEYS_PLAYER = "actions_player1"
_KEYBOARD_ACTIONS = "actions_keyboard"

type _ComboKey = tuple[frozenset[str], bool]


def _profile_candidates(rom: Path, system: str, emulator: str, core: str) -> Iterator[Path]:
    """Where a game's profile may be, first to last.

    The game's own (``<rom>.keys`` next to it; inside a ROM folder,
    ``<folder name>.keys`` or the legacy ``pad2.keys``), then the user's and
    the shipped ones, from the most specific name to ``any.keys``.
    """
    if rom.is_dir():
        yield rom / f"{rom.name}.keys"
        yield rom / "pad2.keys"
    else:
        yield rom.parent / f"{rom.name}.keys"
    names = (
        f"{system}.{emulator}.{core}.keys",
        f"{system}.{emulator}.keys",
        f"{system}.keys",
        f"{emulator}.keys",
        "any.keys",
    )
    for base in (_GAMEPADLY_USER_PROFILES, _GAMEPADLY_PROFILES):
        for name in names:
            yield base / name


def find_profile(rom: Path, system: str, emulator: str, core: str) -> Path | None:
    """The game's own profile: the first that exists (see _profile_candidates())."""
    for path in _profile_candidates(rom, system, emulator, core):
        if path.is_file():
            _logger.debug("pad profile: %s", path)
            return path
    _logger.debug("no pad profile for system=%s emulator=%s core=%s", system, emulator, core)
    return None


def effective_bindings(generator: Generator, system: Emulator) -> dict[HotkeyAction, Binding]:
    """The common bindings, overridden by the emulator's own; unbound actions dropped."""
    merged = {**common_bindings(system), **generator.hotkey_bindings(system)}
    return {action: binding for action, binding in merged.items() if binding is not None}


def hotkey_mappings(
    table: list[HotkeyEntry], bindings: dict[HotkeyAction, Binding]
) -> list[dict[str, Any]]:
    """The pad mappings of the table entries the emulator can perform.

    ``Native`` bindings get none: the emulator reads those combinations itself.
    """
    mappings: list[dict[str, Any]] = []
    taken: set[_ComboKey] = set()
    for entry in table:
        binding = bindings.get(entry.action)
        if isinstance(binding, Keys):
            mapping: dict[str, Any] = {"type": "key", "target": list(binding.codes)}
        elif isinstance(binding, Exec):
            mapping = {"type": "exec", "target": shlex.join(binding.argv)}
        else:
            continue
        mapping = {"trigger": list(entry.trigger), **mapping, "description": entry.action.value}
        if entry.tap:
            mapping["tap"] = True
        # a combination two lines share goes to the first the emulator can perform
        if _combo_key(mapping) in taken:
            continue
        taken.add(_combo_key(mapping))
        mappings.append(mapping)
    return mappings


def keyboard_mappings(
    table: list[HotkeyEntry],
    bindings: dict[HotkeyAction, Binding],
    common: dict[HotkeyAction, Binding | None],
) -> list[dict[str, Any]]:
    """The keyboard mappings of the table entries (commands only)."""
    mappings: list[dict[str, Any]] = []
    for entry in table:
        binding = bindings.get(entry.action)
        if isinstance(binding, Native) or (
            isinstance(binding, Keys) and set(binding.codes) == set(entry.trigger)
        ):
            continue  # the emulator reads this chord itself
        if not isinstance(binding, Exec):
            binding = common.get(entry.action)
        if isinstance(binding, Exec):
            mappings.append({
                "trigger": list(entry.trigger),
                "type": "exec",
                "target": shlex.join(binding.argv),
                "description": entry.action.value,
            })
    return mappings


def _combo_key(mapping: dict[str, Any]) -> _ComboKey:
    """What makes two mappings clash: their inputs, and whether they are taps."""
    def names(value: Any) -> list[str]:
        if value is None:
            return []
        return [value] if isinstance(value, str) else [str(item) for item in value]

    inputs = frozenset(names(mapping.get("trigger")) + names(mapping.get("condition")))
    return inputs, bool(mapping.get("tap", False))


def _read_base(base: Path | None) -> dict[str, Any]:
    """The game's own profile, or an empty one when there is none or it is broken."""
    if base is None:
        return {}
    try:
        data = json.loads(base.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        _logger.warning("ignoring broken gamepad profile %s: %s", base, err)
        return {}
    if not isinstance(data, dict):
        _logger.warning("ignoring gamepad profile %s: not a JSON object", base)
        return {}
    return data


def _merge(own: list[Any], hotkeys: list[dict[str, Any]]) -> tuple[list[Any], int]:
    """The profile's mappings plus the hotkeys whose combination they leave free.

    The universal commands (leave, screenshot, on-screen keyboard) are the
    exception: they take their combination from the profile, which would
    otherwise keep Hotkey+Start for an Alt+F4 that closes nothing, say.
    """
    universal = {action.value for action in UNIVERSAL_ACTIONS}
    commands = {
        _combo_key(mapping)
        for mapping in hotkeys
        if mapping.get("description") in universal and mapping.get("type") == "exec"
    }
    own = [
        mapping
        for mapping in own
        if not (isinstance(mapping, dict) and _combo_key(mapping) in commands)
    ]
    taken = {_combo_key(mapping) for mapping in own if isinstance(mapping, dict)}
    added = [mapping for mapping in hotkeys if _combo_key(mapping) not in taken]
    return own + added, len(added)


def compose_profile(
    base: Path | None,
    mappings: list[dict[str, Any]],
    output: Path,
    keyboard: list[dict[str, Any]] | None = None,
) -> Path | None:
    """Write the session profile; None when there is nothing to map at all."""
    profile = _read_base(base)

    # the mapper falls back to "mappings" when a player has no section: player 1
    # keeps those once it gets a section of its own
    player1, added = _merge(
        list(profile.get(_HOTKEYS_PLAYER) or profile.get("mappings") or []), mappings
    )
    if added:
        profile[_HOTKEYS_PLAYER] = player1
    keys, added_keys = _merge(list(profile.get(_KEYBOARD_ACTIONS) or []), keyboard or [])
    if added_keys:
        profile[_KEYBOARD_ACTIONS] = keys

    if not any(key.startswith("actions_") or key == "mappings" for key in profile):
        return None

    try:
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        output.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    except OSError as err:
        _logger.warning("cannot write the gamepad profile %s: %s", output, err)
        return base
    _logger.debug(
        "gamepad profile %s: %s + %d pad and %d keyboard hotkey(s)",
        output, base or "no base profile", added, added_keys,
    )
    return output


def build_session_profile(
    generator: Generator, system: Emulator, base: Path | None, output: Path
) -> Path | None:
    """Compose the session profile for this game (see the module docstring)."""
    bindings = effective_bindings(generator, system)
    return compose_profile(
        base,
        hotkey_mappings(load_table(), bindings),
        output,
        keyboard_mappings(load_table(KEYBOARD_SECTION), bindings, common_bindings(system)),
    )
