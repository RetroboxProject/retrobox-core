"""Texts of the settings window, from i18n/<language>.yaml.

en.yaml is the reference and the fallback, key by key: a language file may
lack some keys. The language is chosen as for the rest of Retrobox's screens
(EmulationStation's, else the system locale, see retrobox.utils.language).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import yaml

from retrobox.utils.language import DEFAULT_LANGUAGE, pick_language

_DIR: Final = Path(__file__).with_name("i18n")


def available_languages() -> list[str]:
    """The languages there is a file for."""
    return sorted(path.stem for path in _DIR.glob("*.yaml"))


def _load(language: str) -> dict[str, str]:
    try:
        data = yaml.safe_load((_DIR / f"{language}.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


class Translator:
    """Look texts up by id, in one language with English as the fallback."""

    def __init__(self, es_language: str = "", language: str | None = None) -> None:
        self.language = language or pick_language(es_language, available_languages())
        self._texts = _load(DEFAULT_LANGUAGE)
        if self.language != DEFAULT_LANGUAGE:
            self._texts.update(_load(self.language))

    def __call__(self, key: str, **fields: object) -> str:
        """The text ``key``, with its ``{fields}`` filled; the key itself if unknown."""
        text = self._texts.get(key, key)
        return text.format(**fields) if fields else text

    def optional(self, key: str) -> str:
        """The text ``key``, or "" when there is none (e.g. a help line)."""
        return self(key) if key in self._texts else ""
