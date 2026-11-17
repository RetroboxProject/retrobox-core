"""The ROM folders created on start, with their _info.txt."""

from __future__ import annotations

from pathlib import Path

import pytest

from retrobox.startup.frontend_conf import roms_dirs, system_list_generator

_SYSTEMS = {
    "snes.yaml": """
snes:
  fullname: Super Nintendo
  extension: [.sfc, .SMC, .zip, .sfc]
  emulators:
    libretro:
      cores:
        snes9x: {default: true}
        bsnes: {}
""",
    "moved.yaml": """
moved:
  fullname: Moved elsewhere
  path: /somewhere/else
  extension: [.bin]
  emulators:
    libretro:
      cores:
        core: {default: true}
""",
    "group.yaml": """
group:
  fullname: A group, without emulators
""",
}


@pytest.fixture(name="systems")
def fixture_systems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A small systems tree, and an empty ROMs folder the modules use."""
    systems = tmp_path / "systems"
    systems.mkdir()
    for name, text in _SYSTEMS.items():
        (systems / name).write_text(text, encoding="utf-8")
    roms = tmp_path / "roms"
    roms.mkdir()
    monkeypatch.setattr(roms_dirs, "ROMS", roms)
    monkeypatch.setattr(system_list_generator, "ROMS", roms)
    return systems


def test_creates_folders_with_info(systems: Path, tmp_path: Path) -> None:
    """Systems with emulators and no path of their own get a folder and an _info.txt."""
    assert roms_dirs.create_roms_dirs(systems) == 1
    roms = tmp_path / "roms"
    assert sorted(path.name for path in roms.iterdir()) == ["snes"]
    info = (roms / "snes" / roms_dirs.INFO_FILE).read_text(encoding="utf-8")
    assert "SUPER NINTENDO" in info
    assert ".sfc" in info and ".smc" in info
    assert info.count(".sfc") == 1, "extensions are listed once"
    assert "snes9x" in info
    assert str(tmp_path) not in info, "no paths of this machine"


def test_existing_info_is_kept(systems: Path, tmp_path: Path) -> None:
    """An _info.txt that is already there is never rewritten."""
    folder = tmp_path / "roms" / "snes"
    folder.mkdir()
    (folder / roms_dirs.INFO_FILE).write_text("mine", encoding="utf-8")
    assert roms_dirs.create_roms_dirs(systems) == 0
    assert (folder / roms_dirs.INFO_FILE).read_text(encoding="utf-8") == "mine"


def test_deleted_info_comes_back(systems: Path, tmp_path: Path) -> None:
    """Deleting the _info.txt of an existing folder gets it written again."""
    folder = tmp_path / "roms" / "snes"
    folder.mkdir()
    assert roms_dirs.create_roms_dirs(systems) == 0
    assert (folder / roms_dirs.INFO_FILE).is_file()


def test_missing_roms_folder_creates_nothing(
    systems: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the ROMs folder missing (an unmounted drive), nothing is created."""
    unplugged = tmp_path / "unplugged" / "roms"
    monkeypatch.setattr(roms_dirs, "ROMS", unplugged)
    monkeypatch.setattr(system_list_generator, "ROMS", unplugged)
    assert roms_dirs.create_roms_dirs(systems) == 0
    assert not unplugged.exists()


def test_setting_turns_it_off(
    systems: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[core] create_rom_folders = false creates nothing."""
    monkeypatch.setattr(
        roms_dirs, "get_ini_value", lambda section, key, default="": "false"
    )
    assert roms_dirs.create_roms_dirs(systems) == 0
    assert not any((tmp_path / "roms").iterdir())


def test_info_for_every_shipped_system() -> None:
    """The text can be written for every shipped system (no crash on odd YAML)."""
    for name, content in system_list_generator.load_systems():
        text = roms_dirs.info_text(name, content)
        assert text.endswith("\n")
        assert all(len(line) <= 79 for line in text.splitlines()), name
