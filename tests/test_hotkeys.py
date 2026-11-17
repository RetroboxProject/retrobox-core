"""The hotkeys' feature lookups against the shipped feature files."""

from retrobox.configgen.hotkeys import _has_osk_feature


def test_the_browsers_have_the_osk() -> None:
    """Chrome and Firefox list ``osk`` in their feature files."""
    assert _has_osk_feature("chrome", "chrome")
    assert _has_osk_feature("firefox", None)


def test_other_emulators_do_not() -> None:
    """An emulator (or core) whose feature file lacks it, or that has none, has no osk."""
    assert not _has_osk_feature("libretro", "snes9x")
    assert not _has_osk_feature("no-such-emulator", None)
