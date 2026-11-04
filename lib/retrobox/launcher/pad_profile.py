"""The gamepadly profile of the game being played: its mappings plus the standard hotkeys.

Two layers, merged into ``<runtime dir>/pad2key/session.keys``:

1. the profile gamepadly would pick for the game (per game, system,
   emulator, core; ``share/pad2key/profiles`` and the user's), with the
   full pad-to-keyboard mappings of keyboard-only games;
2. the standard hotkeys (``retrobox.configgen.hotkeys``) for player 1, as
   the emulator performs them.

The first layer wins: a combination it already maps is not touched, so a
game or system profile can still do its own thing with any hotkey.
"""

from __future__ import annotations

import json
import logging
import shlex
from typing import TYPE_CHECKING, Any

from retrobox.configgen.hotkeys import (
    Exec,
    HotkeyAction,
    Keys,
    common_bindings,
    load_table,
)

if TYPE_CHECKING:
    from pathlib import Path

    from retrobox.configgen.Emulator import Emulator
    from retrobox.configgen.generators.Generator import Generator
    from retrobox.configgen.hotkeys import Binding, HotkeyEntry

_logger = logging.getLogger(__name__)

_HOTKEYS_PLAYER = "actions_player1"

type _ComboKey = tuple[frozenset[str], bool]


def effective_bindings(generator: Generator, system: Emulator) -> dict[HotkeyAction, Binding]:
    """The common bindings, overridden by the emulator's own; unbound actions dropped."""
    merged = {**common_bindings(), **generator.hotkey_bindings(system)}
    return {action: binding for action, binding in merged.items() if binding is not None}


def hotkey_mappings(
    table: list[HotkeyEntry], bindings: dict[HotkeyAction, Binding]
) -> list[dict[str, Any]]:
    """The gamepadly mappings of the table entries the emulator can perform.

    ``Native`` bindings get none: the emulator reads those combinations itself.
    """
    mappings: list[dict[str, Any]] = []
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
        mappings.append(mapping)
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


def compose_profile(
    base: Path | None, mappings: list[dict[str, Any]], output: Path
) -> Path | None:
    """Write the session profile; None when there is nothing to map at all."""
    profile = _read_base(base)

    # gamepadly falls back to "mappings" when a player has no section: player 1
    # keeps those once it gets a section of its own
    player1 = list(profile.get(_HOTKEYS_PLAYER) or profile.get("mappings") or [])
    taken = {_combo_key(mapping) for mapping in player1 if isinstance(mapping, dict)}
    added = [mapping for mapping in mappings if _combo_key(mapping) not in taken]
    if added:
        profile[_HOTKEYS_PLAYER] = player1 + added

    if not any(key.startswith("actions_") or key == "mappings" for key in profile):
        return None

    try:
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        output.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    except OSError as err:
        _logger.warning("cannot write the gamepad profile %s: %s", output, err)
        return base
    _logger.debug(
        "gamepad profile %s: %s + %d hotkey(s)", output, base or "no base profile", len(added)
    )
    return output


def build_session_profile(
    generator: Generator, system: Emulator, base: Path | None, output: Path
) -> Path | None:
    """Compose the session profile for this game (see the module docstring)."""
    mappings = hotkey_mappings(load_table(), effective_bindings(generator, system))
    return compose_profile(base, mappings, output)
