"""Tests for the launcher file parser of the Firefox generator."""
from retrobox.configgen.generators.firefox.firefoxGenerator import _parse_rom_launcher


def test_kodi_webapp_format() -> None:
    """Kodi webapp format."""
    lines = ["[kodi_webapp]", "name=YT", "url=https://a.b/?x=1", "user_agent=UA 1.0"]
    assert _parse_rom_launcher(lines) == ("https://a.b/?x=1", "UA 1.0")


def test_kodi_webapp_without_user_agent() -> None:
    """Kodi webapp without user agent."""
    assert _parse_rom_launcher(["[kodi_webapp]", "url=https://a.b"]) == ("https://a.b", None)


def test_plain_format_still_works() -> None:
    """Plain format still works."""
    assert _parse_rom_launcher(["https://a.b/?run=1", "UA"]) == ("https://a.b/?run=1", "UA")
