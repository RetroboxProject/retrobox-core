"""Tests for the .webapp file parser of the Chrome generator."""
from retrobox.configgen.generators.chrome.chromeGenerator import parse_webapp


def test_ini_format() -> None:
    """Ini format."""
    text = "[kodi_webapp]\nname=YT\nurl=https://a.b/?x=1#y\nuser_agent=Mozilla/5.0 (X11)\n"
    assert parse_webapp(text) == ("https://a.b/?x=1#y", "Mozilla/5.0 (X11)")


def test_ini_without_user_agent() -> None:
    """Ini without user agent."""
    assert parse_webapp("[kodi_webapp]\nurl=https://a.b\n") == ("https://a.b", None)


def test_legacy_format() -> None:
    """Legacy format."""
    assert parse_webapp("https://a.b\nUA\n") == ("https://a.b", "UA")
    assert parse_webapp("https://a.b\n") == ("https://a.b", None)


def test_empty() -> None:
    """Empty."""
    assert parse_webapp("") == ("about:blank", None)
