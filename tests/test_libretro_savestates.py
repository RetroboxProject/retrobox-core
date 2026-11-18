"""When RetroArch loads the automatic state, which the overlay's Quit follows."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from retrobox.configgen.config import SystemConfig
from retrobox.configgen.generators.libretro.libretroConfig import loads_auto_state

if TYPE_CHECKING:
    from retrobox.configgen.Emulator import Emulator

ACHIEVEMENTS = {
    "retroachievements": "1",
    "retroachievements.username": "player",
    "retroachievements.token": "tok123",
}


def _system(**values: str) -> Emulator:
    data = {key.replace("__", "."): value for key, value in values.items()}
    return cast("Emulator", SimpleNamespace(config=SystemConfig(data)))


def test_the_auto_save_option_decides() -> None:
    """EmulationStation's auto save/load turns it on; it is off by default."""
    assert loads_auto_state(_system(autosave="1"))
    assert not loads_auto_state(_system(autosave="0"))
    assert not loads_auto_state(_system())


def test_hardcore_keeps_it_off() -> None:
    """Hardcore mode keeps states away, the automatic one too."""
    assert not loads_auto_state(
        _system(autosave="1", retroachievements__hardcore="1", **_dotted(ACHIEVEMENTS))
    )
    assert loads_auto_state(_system(autosave="1", **_dotted(ACHIEVEMENTS)))


def _dotted(values: dict[str, str]) -> dict[str, str]:
    """Keyword-friendly keys (``a__b`` for ``a.b``)."""
    return {key.replace(".", "__"): value for key, value in values.items()}
