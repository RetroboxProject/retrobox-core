"""The order in which a game's bezel is looked up."""

from __future__ import annotations

from pathlib import Path

import pytest

from retrobox.configgen.utils import bezels


@pytest.fixture(name="roots")
def fixture_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Empty user and default decoration folders, used by the lookup."""
    user = tmp_path / "decorations"
    default = tmp_path / "decorations-default"
    monkeypatch.setattr(bezels, "_DECORATIONS_DIR", user)
    monkeypatch.setattr(bezels, "_DECORATIONS_DEF_DIR", default)
    return user, default


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _found(
    screen: tuple[int, int] | None = None, rom: str = "/roms/megadrive/Sonic.md"
) -> Path | None:
    infos = bezels.get_bezel_infos(rom, "set", "megadrive", "retroarch", screen)
    return None if infos is None else infos["png"]


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1920, 1080), ["16_9"]),
        ((1280, 800), ["16_10", "8_5"]),
        ((2560, 1080), ["21_9", "64_27"]),
        ((1024, 768), ["4_3"]),
        ((0, 1080), []),
    ],
)
def test_ratio_suffixes(size: tuple[int, int], expected: list[str]) -> None:
    """Named ratios within the tolerance first, then the screen's own fraction."""
    assert bezels.ratio_suffixes(*size) == expected


def test_nothing_found(roots: tuple[Path, Path]) -> None:
    """No file at all: no bezel."""
    del roots
    assert _found((1920, 1080)) is None


def test_game_beats_system_beats_default(roots: tuple[Path, Path]) -> None:
    """games/<system>/<rom> > games/<rom> > systems/<system> > default."""
    user, _ = roots
    default = _touch(user / "set" / "default.png")
    assert _found() == default
    system = _touch(user / "set" / "systems" / "megadrive.png")
    assert _found() == system
    any_system = _touch(user / "set" / "games" / "Sonic.png")
    assert _found() == any_system
    this_system = _touch(user / "set" / "games" / "megadrive" / "Sonic.png")
    assert _found() == this_system


def test_user_decorations_beat_defaults(roots: tuple[Path, Path]) -> None:
    """The same file in decorations/ wins over decorations-default/."""
    user, default = roots
    _touch(default / "set" / "systems" / "megadrive.png")
    mine = _touch(user / "set" / "systems" / "megadrive.png")
    assert _found() == mine


def test_default_set_game_bezel_beats_user_default(roots: tuple[Path, Path]) -> None:
    """Every candidate of the user root comes first, even a generic one."""
    user, default = roots
    generic = _touch(user / "set" / "default.png")
    _touch(default / "set" / "games" / "megadrive" / "Sonic.png")
    assert _found() == generic


def test_ratio_bezel_comes_first(roots: tuple[Path, Path]) -> None:
    """A bezel made for the screen's ratio beats even a game's plain bezel."""
    user, default = roots
    _touch(user / "set" / "games" / "megadrive" / "Sonic.png")
    ratio = _touch(default / "set" / "systems" / "megadrive_16_10.png")
    assert _found((1280, 800)) == ratio
    # on a 16:9 screen it doesn't apply
    assert _found((1920, 1080)) == user / "set" / "games" / "megadrive" / "Sonic.png"


def test_ratio_variant_carries_its_files(roots: tuple[Path, Path]) -> None:
    """The .info, .lay and .zip of a ratio bezel carry the suffix too."""
    user, _ = roots
    _touch(user / "set" / "systems" / "megadrive_4_3.png")
    infos = bezels.get_bezel_infos("Sonic.md", "set", "megadrive", "retroarch", (1024, 768))
    assert infos is not None
    assert infos["info"].name == "megadrive_4_3.info"
    assert infos["layout"].name == "megadrive_4_3.lay"
    assert infos["mamezip"].name == "megadrive_4_3.zip"
    assert infos["specific_to_game"] is False


def test_read_bezel_infos_tolerates_bad_files(tmp_path: Path) -> None:
    """A missing or broken .info reads as empty."""
    assert not bezels.read_bezel_infos(tmp_path / "missing.info")
    broken = tmp_path / "broken.info"
    broken.write_text("{not json", encoding="utf-8")
    assert not bezels.read_bezel_infos(broken)
    good = tmp_path / "good.info"
    good.write_text('{"width": 1920, "top": 24}', encoding="utf-8")
    assert bezels.read_bezel_infos(good) == {"width": 1920, "top": 24}
