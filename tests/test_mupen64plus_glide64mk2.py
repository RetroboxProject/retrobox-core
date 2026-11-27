"""Glide64mk2's options in mupen64plus.cfg: the render height of Retrobox's patch."""

from __future__ import annotations

import pytest

from retrobox.configgen.config import SystemConfig
from retrobox.configgen.generators.mupen64plus import mupen64plus_config
from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser


def _glide64mk2(options: dict[str, str]) -> dict[str, str]:
    """The Video-Glide64mk2 section written for the options."""
    ini = CaseSensitiveConfigParser(interpolation=None)
    # pylint: disable-next=protected-access
    mupen64plus_config._write_glide64mk2(ini, SystemConfig(options))
    return dict(ini["Video-Glide64mk2"])


def test_render_height_defaults_to_the_window() -> None:
    """Without the option the plugin draws at the window's size (RenderHeight 0)."""
    assert _glide64mk2({})["RenderHeight"] == "0"


@pytest.mark.parametrize("height", ["240", "480", "720", "960", "1080"])
def test_render_height_is_the_choice(height: str) -> None:
    """The height chosen in the menu goes to RenderHeight as it is."""
    section = _glide64mk2({"mupen64plus_glide64mk2_RenderHeight": height})
    assert section["RenderHeight"] == height
