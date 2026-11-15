"""Choosing the language of Retrobox's own screens.

The language is EmulationStation's own (``Language`` in es_settings.cfg) when
it was set there, else the system locale (``LANGUAGE``, ``LC_ALL``,
``LC_MESSAGES``, ``LANG``), else English. Only the language part of a locale
is used (``pt_BR`` -> ``pt``).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping

DEFAULT_LANGUAGE: Final = "en"

_LOCALE_VARIABLES: Final = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")


def _code(locale: str) -> str:
    """``es_ES.UTF-8`` -> ``es``; empty for the C/POSIX locale."""
    code = locale.strip().split(".", 1)[0].split("@", 1)[0].replace("-", "_").split("_", 1)[0]
    return "" if code.upper() in ("", "C", "POSIX") else code.lower()


def _candidates(es_language: str, environ: Mapping[str, str]) -> Iterable[str]:
    """Locales to try, most preferred first."""
    yield es_language
    for variable in _LOCALE_VARIABLES:
        # LANGUAGE is a colon-separated list of preferences
        yield from environ.get(variable, "").split(":")


def pick_language(
    es_language: str,
    supported: Collection[str],
    environ: Mapping[str, str] | None = None,
) -> str:
    """The first supported language among ES's setting and the system locale.

    Args:
        es_language: ``Language`` of es_settings.cfg (e.g. ``es_ES``), if set.
        supported: Language codes to choose from.
        environ: The environment to read the locale from (default: os.environ).

    Returns:
        A supported code; DEFAULT_LANGUAGE when nothing better matches.
    """
    environ = os.environ if environ is None else environ
    for candidate in _candidates(es_language, environ):
        code = _code(candidate)
        if code in supported:
            return code
    return DEFAULT_LANGUAGE
