"""The keyboard hotkeys of Mupen64Plus: the pad mapper presses the keys the core listens to."""

from __future__ import annotations

from retrobox.configgen.generators.mupen64plus import mupen64plus_config
from retrobox.configgen.generators.mupen64plus.mupen64plus_generator import Mupen64PlusGenerator
from retrobox.configgen.hotkeys import CLOSE_WINDOW, HotkeyAction, Keys
from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser


def _written() -> CaseSensitiveConfigParser:
    ini = CaseSensitiveConfigParser(interpolation=None)
    # a mupen64plus.cfg of an older core, with the keys somewhere else
    ini.add_section("CoreEvents")
    ini.set("CoreEvents", "Kbd Mapping Save State", "0")
    ini.set("CoreEvents", "Joy Mapping Stop", '"J0B6/B7"')
    # pylint: disable-next=protected-access
    mupen64plus_config._write_hotkeys(ini)
    return ini


def test_keys_are_written_over_the_ones_of_the_file() -> None:
    """The core gets the keys the pad mapper presses, whatever the file said."""
    ini = _written()
    assert ini.get("CoreEvents", "Kbd Mapping Save State") == "286"
    assert ini.get("CoreEvents", "Kbd Mapping Load State") == "288"
    assert ini.get("CoreEvents", "Kbd Mapping Increment Slot") == "287"
    assert ini.get("CoreEvents", "Kbd Mapping Pause") == "112"
    assert ini.get("CoreEvents", "Kbd Mapping Reset") == "290"
    assert ini.get("CoreEvents", "Kbd Mapping Fast Forward") == "102"


def test_bindings_are_the_same_keys() -> None:
    """The generator binds exit and every action it writes a key for."""
    bindings = Mupen64PlusGenerator().hotkey_bindings(None)
    assert bindings[HotkeyAction.EXIT] == CLOSE_WINDOW
    assert bindings[HotkeyAction.SAVE_STATE] == Keys(("KEY_F5",))
    assert bindings[HotkeyAction.LOAD_STATE] == Keys(("KEY_F7",))
    assert bindings[HotkeyAction.SLOT_NEXT] == Keys(("KEY_F6",))
    assert bindings[HotkeyAction.PAUSE] == Keys(("KEY_P",))
    assert bindings[HotkeyAction.RESET] == Keys(("KEY_F9",))
    assert bindings[HotkeyAction.FAST_FORWARD] == Keys(("KEY_F",))
    assert HotkeyAction.SLOT_PREV not in bindings  # the core has no key for it
