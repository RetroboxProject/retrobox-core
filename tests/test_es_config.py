"""The shipped systems and emulator options, and the ES files built from them."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import SHARE_DIR
from retrobox.configgen.generators import get_generator
from retrobox.paths import DATA_DIR, ES_FEATURES_CFG, ES_SYSTEMS_CFG, RECORDINGS, SCREENSHOTS
from retrobox.paths import SHARE_DIR as INSTALLED_SHARE_DIR
from retrobox.startup.frontend_conf.features_list_generator import generate_es_features
from retrobox.startup.frontend_conf.system_list_generator import (
    expand_system_path,
    generate_es_systems,
)
from retrobox.utils.features_yaml import load_feature_yaml

SYSTEM_FILES = sorted((SHARE_DIR / "systems").rglob("*.yaml"))
OPTION_FILES = sorted((SHARE_DIR / "emulator_options").glob("*.yaml"))

def _load(path: Path) -> tuple[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and len(data) == 1, f"{path}: one system per file"
    name, content = next(iter(data.items()))
    assert isinstance(content, dict), f"{path}: the system's settings must be a mapping"
    return name, content


SYSTEMS = dict(_load(path) for path in SYSTEM_FILES)


def _defaults(content: dict[str, Any]) -> list[tuple[str, str]]:
    """(emulator, core) pairs marked ``default: true`` in a system."""
    return [
        (emulator, core)
        for emulator, emulator_data in (content.get("emulators") or {}).items()
        for core, core_data in ((emulator_data or {}).get("cores") or {}).items()
        if (core_data or {}).get("default")
    ]


@pytest.mark.parametrize("path", SYSTEM_FILES, ids=lambda path: path.stem)
def test_system_key_matches_file_name(path: Path) -> None:
    """The key of a system file is its name, and its file is named after it."""
    name, _ = _load(path)
    assert name == path.stem


def test_system_names_are_unique() -> None:
    """No two files define the same system."""
    names = Counter(_load(path)[0] for path in SYSTEM_FILES)
    assert [name for name, count in names.items() if count > 1] == []


def test_every_system_has_extensions() -> None:
    """A system with emulators says which files it runs."""
    missing = [
        name for name, content in SYSTEMS.items()
        if content.get("emulators") and not content.get("extension")
    ]
    assert missing == []


def test_one_default_emulator_per_system() -> None:
    """Exactly one emulator and core is the default of each system."""
    several = {name: _defaults(c) for name, c in SYSTEMS.items() if len(_defaults(c)) > 1}
    assert several == {}
    without = sorted(
        name for name, content in SYSTEMS.items()
        if content.get("emulators") and not _defaults(content)
    )
    assert without == [], f"no default emulator: {without}"


@pytest.mark.parametrize(
    "emulator",
    sorted({emu for content in SYSTEMS.values() for emu in content.get("emulators") or {}}),
)
def test_every_emulator_has_a_generator(emulator: str) -> None:
    """Each emulator a system offers can be built (its generator imports and is concrete)."""
    assert get_generator(emulator, "") is not None


@pytest.mark.parametrize("path", OPTION_FILES, ids=lambda path: path.stem)
def test_option_files_load(path: Path) -> None:
    """Every emulator options file is valid YAML with an emulator name."""
    data = load_feature_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("emulator_name"), "emulator_name is required"


@pytest.fixture(name="es_home")
def fixture_es_home() -> Path:
    """EmulationStation's home in the session sandbox (the generators link into it)."""
    ES_SYSTEMS_CFG.parent.mkdir(parents=True, exist_ok=True)
    return ES_SYSTEMS_CFG.parent


def test_es_systems_cfg(es_home: Path, tmp_path: Path) -> None:
    """es_systems.cfg lists every system with emulators, each with a path and a command."""
    output = tmp_path / "es_systems.cfg"
    generate_es_systems(output_path=output)
    root = ET.parse(output).getroot()
    assert root.tag == "systemList"

    listed = {system.findtext("name"): system for system in root.iter("system")}
    assert set(listed) == set(SYSTEMS)
    for name, system in listed.items():
        # ES doesn't resolve relative paths: they would follow its working directory
        assert Path(system.findtext("path") or "").is_absolute(), f"{name}: path not absolute"
        assert "{" not in (system.findtext("path") or ""), f"{name}: unexpanded placeholder"
        assert system.findtext("command"), f"{name}: no command"
    assert (es_home / "es_systems.cfg").resolve() == output.resolve()


def test_es_systems_cfg_keeps_one_default(es_home: Path, tmp_path: Path) -> None:
    """The default core of a system survives into the XML."""
    del es_home
    output = tmp_path / "es_systems.cfg"
    generate_es_systems(output_path=output)
    systems = ET.parse(output).getroot().iter("system")
    snes = next(system for system in systems if system.findtext("name") == "snes")
    defaults = [
        (emulator.get("name"), core.text)
        for emulator in snes.iter("emulator")
        for core in emulator.iter("core")
        if core.get("default") == "true"
    ]
    assert defaults == _defaults(SYSTEMS["snes"])


def test_es_features_cfg(
    es_home: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """es_features.cfg builds without warnings.

    The generator itself warns about names outside the menu vocabulary and
    about shared features that are referenced but never defined.
    """
    output = tmp_path / "es_features.cfg"
    with caplog.at_level(logging.WARNING):
        generate_es_features(output_path=output)
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings == []

    root = ET.parse(output).getroot()
    assert root.tag == "features"
    emulators = {element.get("name") for element in root.iter("emulator")}
    assert {"libretro", "dolphin", "pcsx2", "ppsspp", "cemu"} <= emulators
    assert (es_home / "es_features.cfg").resolve() == output.resolve()
    assert ES_FEATURES_CFG.is_symlink()


def test_es_features_warns_about_undefined_shared_features(
    es_home: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The warning the previous test relies on is really raised (and captured)."""
    del es_home
    options = tmp_path / "emulator_options"
    options.mkdir()
    (options / "_global_config.yaml").write_text(
        (SHARE_DIR / "emulator_options" / "_global_config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (options / "fake.yaml").write_text(
        "emulator_name: fake\nsharedFeatures:\n  - no_such_feature\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        generate_es_features(options, output_path=tmp_path / "es_features.cfg")
    assert any("no_such_feature" in record.getMessage() for record in caplog.records)


def test_standalone_emulators_offer_achievements(es_home: Path, tmp_path: Path) -> None:
    """PCSX2, Dolphin and Flycast carry the cheevos feature (ES hashes their games)."""
    del es_home
    output = tmp_path / "es_features.cfg"
    generate_es_features(output_path=output)
    features = {
        element.get("name"): (element.get("features") or "").split(",")
        for element in ET.parse(output).getroot().iter("emulator")
    }
    for emulator in ("pcsx2", "dolphin", "flycast"):
        assert "cheevos" in features[emulator], emulator


def test_retrobox_systems_use_the_data_folders(es_home: Path, tmp_path: Path) -> None:
    """Image viewer, recordings, library and apps live in the user's data folders."""
    del es_home
    output = tmp_path / "es_systems.cfg"
    generate_es_systems(output_path=output)
    systems = ET.parse(output).getroot().iter("system")
    paths = {system.findtext("name"): system.findtext("path") for system in systems}
    assert paths["imageviewer"] == str(SCREENSHOTS)
    assert paths["recordings"] == str(RECORDINGS)
    assert paths["library"] == str(DATA_DIR / "library")
    assert paths["apps"] == str(DATA_DIR / "apps")
    assert paths["linuxapps"] == str(DATA_DIR / "linuxapps")
    assert paths["emuconfig"] == str(INSTALLED_SHARE_DIR / "es_menu")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{screenshots}", SCREENSHOTS),
        ("{data}/library", DATA_DIR / "library"),
        ("games/extra", DATA_DIR / "games" / "extra"),
        ("/srv/games", Path("/srv/games")),
    ],
)
def test_expand_system_path(text: str, expected: Path) -> None:
    """Placeholders become Retrobox's folders; relative paths start at the data folder."""
    assert expand_system_path(text) == expected


def test_expand_system_path_home_and_unknown() -> None:
    """``~`` is the home; an unknown placeholder is an error, not a literal folder."""
    assert expand_system_path("~/games") == Path.home() / "games"
    with pytest.raises(ValueError, match="unknown placeholder"):
        expand_system_path("{nowhere}/games")
