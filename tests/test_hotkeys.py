"""The hotkeys' feature lookups against the shipped feature files."""

from pathlib import Path

from retrobox.configgen.hotkeys import PAD_SECTION, HotkeyAction, _has_osk_feature, load_table


def test_the_browsers_have_the_osk() -> None:
    """Chrome and Firefox list ``osk`` in their feature files."""
    assert _has_osk_feature("chrome", "chrome")
    assert _has_osk_feature("firefox", None)


def test_other_emulators_do_not() -> None:
    """An emulator (or core) whose feature file lacks it, or that has none, has no osk."""
    assert not _has_osk_feature("libretro", "snes9x")
    assert not _has_osk_feature("no-such-emulator", None)


def test_a_line_can_be_kept_to_some_emulators(tmp_path: Path) -> None:
    """``emulators`` keeps a line to those emulators (one name may stand alone);
    without it, it is everyone's; a line with a bad one is dropped."""
    table = tmp_path / "hotkeys.yaml"
    table.write_text(
        "pad:\n"
        "  - {action: exit, trigger: [hotkey, start]}\n"
        "  - {action: menu, trigger: [hotkey, b], emulators: [libretro]}\n"
        "  - {action: pause, trigger: [hotkey, a], emulators: libretro}\n"
        "  - {action: reset, trigger: [hotkey, y], emulators: 3}\n",
        encoding="utf-8",
    )
    missing = tmp_path / "missing.yaml"

    def actions(emulator: str | None) -> list[str]:
        entries = load_table(PAD_SECTION, missing, table, emulator=emulator)
        return [entry.action.value for entry in entries]

    assert actions("libretro") == ["exit", "menu", "pause"]
    assert actions("pcsx2") == ["exit"]
    assert actions(None) == ["exit", "menu", "pause"]


def test_the_shipped_menu_line_is_retroarch_s() -> None:
    """Hotkey+B is RetroArch's menu, and nobody else's."""
    menu = [entry for entry in load_table() if entry.action is HotkeyAction.MENU]
    assert [(entry.trigger, entry.emulators) for entry in menu] == [
        (("hotkey", "b"), ("libretro",))
    ]
