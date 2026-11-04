"""Environment shared by the generators of PC game clients (Heroic, Lutris)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from retrobox.configgen.controller import generate_sdl_game_controller_config
from retrobox.configgen.utils.language import _raw_locale_token

if TYPE_CHECKING:
    from pathlib import Path

    from retrobox.configgen.controller import Controllers
    from retrobox.configgen.Emulator import Emulator


_FALLBACK_LOCALE = "en_US.UTF-8"


def utf8_locale() -> str:
    """The system's locale as a UTF-8 locale name (``es_ES.UTF-8``).

    Only ``language_COUNTRY`` tokens make a locale name: a bare language
    (``es``) does not, so it falls back to ``en_US.UTF-8``.
    """
    token = _raw_locale_token()
    language, _, country = token.partition("_")
    if len(language) < 2 or len(country) != 2:
        return _FALLBACK_LOCALE
    return f"{language.lower()}_{country.upper()}.UTF-8"


def launcher_environment(system: Emulator, controllers: Controllers) -> dict[str, str | Path]:
    """Locale, and the controllers' SDL mappings unless ``sdl_config`` is off."""
    locale_name = utf8_locale()
    environment: dict[str, str | Path] = {"LANG": locale_name, "LC_ALL": locale_name}
    if system.config.get_bool("sdl_config", True):
        environment["SDL_GAMECONTROLLERCONFIG"] = generate_sdl_game_controller_config(controllers)
        environment["SDL_JOYSTICK_HIDAPI"] = "0"
    return environment
