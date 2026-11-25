"""Render sizes whose ``auto`` follows the screen (``screen_auto`` in a core YAML)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from retrobox.configgen.generators.libretro.libretro_core_options import (
    fit_screen,
    parse_core_features,
)

_SIZES_43 = ((320, 240), (640, 480), (960, 720), (1280, 960), (1440, 1080))
_MUPEN_YAML = (
    Path(__file__).resolve().parents[1]
    / "share" / "emulator_options" / "libretro_mupen64plus-next.yaml"
)


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (1920, 1080, "1440x1080"),
        (1366, 768, "960x720"),
        (1280, 720, "960x720"),
        (3840, 2160, "1440x1080"),
        (1080, 1920, "1440x1080"),  # a rotated screen is drawn landscape
        (300, 200, "320x240"),  # nothing fits: the smallest size
    ],
)
def test_fit_screen(width: int, height: int, expected: str) -> None:
    """Auto takes the largest size whose two sides fit in the screen."""
    assert fit_screen(_SIZES_43, {"width": width, "height": height}) == expected


def test_auto_follows_the_screen_only_when_asked() -> None:
    """``screen_auto`` turns ``auto`` into a size; without it, auto is the core default."""
    data = {"groups": {"GENERAL": {"submenus": {"SCREEN": [
        {"value": "fit", "screen_auto": True,
         "choices": [{"value": "auto"}, {"value": "640x480"}, {"value": "1280x960"}]},
        {"value": "plain", "choices": [{"value": "auto"}, {"value": "640x480"}]},
    ]}}}}
    fit, plain = parse_core_features(data)
    screen = {"width": 1920, "height": 1080}
    assert fit.options_for(None, screen) == {"fit": "1280x960"}
    assert fit.options_for("auto", screen) == {"fit": "1280x960"}
    assert fit.options_for("640x480", screen) == {"fit": "640x480"}
    assert fit.options_for("auto") == {}
    assert plain.options_for("auto", screen) == {}


def test_mupen64plus_next_sizes_stop_at_1080p() -> None:
    """Every render size of mupen64plus_next fits in 1080 lines."""
    with _MUPEN_YAML.open(encoding="utf-8") as file:
        features = parse_core_features(yaml.safe_load(file))
    sized = [feature for feature in features if feature.screen_sizes]
    assert {feature.option for feature in sized} == {
        "mupen64plus-43screensize", "mupen64plus-169screensize"}
    for feature in sized:
        assert all(height <= 1080 for _, height in feature.screen_sizes)
