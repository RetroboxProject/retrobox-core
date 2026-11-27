"""The overscan of Mupen64Plus: the pixels GLideN64 and Glide64mk2 crop at the picture's edges."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from retrobox.configgen.config import SystemConfig
from retrobox.configgen.generators.mupen64plus import mupen64plus_config
from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser

OPTIONS = Path(__file__).resolve().parents[1] / "share" / "emulator_options" / "mupen64plus.yaml"
HORIZONTAL = "mupen64plus_OverscanHorizontal"
VERTICAL = "mupen64plus_OverscanVertical"
SIDES = ("Left", "Right", "Top", "Bottom")
STANDARDS = ("Pal", "Ntsc")


def _new_ini() -> CaseSensitiveConfigParser:
    return CaseSensitiveConfigParser(interpolation=None)


def _gliden64(options: dict[str, str], data_dir: Path) -> dict[str, str]:
    """The Video-GLideN64 section written for the options."""
    ini = _new_ini()
    # pylint: disable-next=protected-access
    mupen64plus_config._write_gliden64(ini, SystemConfig(options), data_dir)
    return dict(ini["Video-GLideN64"])


def _glide64mk2(options: dict[str, str]) -> dict[str, str]:
    """The Video-Glide64mk2 section written for the options."""
    ini = _new_ini()
    # pylint: disable-next=protected-access
    mupen64plus_config._write_glide64mk2(ini, SystemConfig(options))
    return dict(ini["Video-Glide64mk2"])


def test_overscan_is_off_by_default(tmp_path: Path) -> None:
    """Without options nothing is cropped, in either plugin."""
    section = _gliden64({}, tmp_path)
    assert section["EnableOverscan"] == "False"
    cropped = {section[f"Overscan{standard}{side}"] for standard in STANDARDS for side in SIDES}
    assert cropped == {"0"}
    mk2 = _glide64mk2({})
    assert (mk2["OverscanHorizontal"], mk2["OverscanVertical"]) == ("0", "0")


def test_gliden64_crops_the_same_pixels_in_pairs_and_in_both_standards(tmp_path: Path) -> None:
    """Left and right take the horizontal pixels, top and bottom the vertical ones."""
    section = _gliden64({HORIZONTAL: "7", VERTICAL: "3"}, tmp_path)
    assert section["EnableOverscan"] == "True"
    for standard in STANDARDS:
        assert section[f"Overscan{standard}Left"] == section[f"Overscan{standard}Right"] == "7"
        assert section[f"Overscan{standard}Top"] == section[f"Overscan{standard}Bottom"] == "3"


@pytest.mark.parametrize(("horizontal", "vertical"), [("5", "0"), ("0", "5")])
def test_gliden64_one_direction_is_enough_to_enable_it(
    tmp_path: Path, horizontal: str, vertical: str
) -> None:
    """The crop is on when either of the two is not zero, and the other stays at zero."""
    section = _gliden64({HORIZONTAL: horizontal, VERTICAL: vertical}, tmp_path)
    assert section["EnableOverscan"] == "True"
    assert section["OverscanNtscLeft"] == horizontal
    assert section["OverscanNtscTop"] == vertical


def test_glide64mk2_gets_the_pixels_of_the_menu() -> None:
    """The patched plugin reads the two options as they are."""
    section = _glide64mk2({HORIZONTAL: "12", VERTICAL: "20"})
    assert (section["OverscanHorizontal"], section["OverscanVertical"]) == ("12", "20")


@pytest.mark.parametrize(
    ("value", "pixels"),
    [
        ("0", 0), ("20", 20), (7, 7), ("21", 20), ("999", 20),
        ("-4", 0), ("", 0), ("a lot", 0), ("2.5", 0),
    ],
)
def test_overscan_stays_between_zero_and_twenty(value: str | int, pixels: int) -> None:
    """What a hand-edited option says is brought into the 0 to 20 the plugins are given."""
    config = SystemConfig({HORIZONTAL: value})
    assert mupen64plus_config.overscan(config, "OverscanHorizontal") == pixels


def test_rice_is_left_alone() -> None:
    """Rice has no overscan: its section is not given the options of the others."""
    ini = _new_ini()
    config = SystemConfig({"core": "rice", HORIZONTAL: "9", VERTICAL: "9"})
    # pylint: disable-next=protected-access
    mupen64plus_config._write_rice(ini, config)
    assert not any("Overscan" in key for key in ini["Video-Rice"])


def test_menu_offers_zero_to_the_maximum() -> None:
    """Both options of the menu go from 0 (the default, first) to the most the plugins take."""
    data = yaml.safe_load(OPTIONS.read_text(encoding="utf-8"))
    screen = {item["value"]: item for item in data["groups"]["GENERAL"]["submenus"]["SCREEN"]}
    for key in (HORIZONTAL, VERTICAL):
        values = [choice["value"] for choice in screen[key]["choices"]]
        assert values == list(range(mupen64plus_config.MAX_OVERSCAN + 1))


@pytest.mark.parametrize(
    ("options", "expected"),
    [({}, "True"), ({"mupen64plus_WaitForGPU": "False"}, "False")],
)
def test_glide64mk2_waits_for_the_gpu_unless_told_not_to(
    options: dict[str, str], expected: str
) -> None:
    """The plugin keeps its glFinish at each frame by default."""
    assert _glide64mk2(options)["WaitForGPU"] == expected
