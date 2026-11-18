"""Where the executable of an emulator is found (EmulatorBinary)."""

from __future__ import annotations

from pathlib import Path

import pytest

from retrobox.configgen.exceptions import RetroboxException
from retrobox.configgen.utils.emulator_binary import EmulatorBinary
from retrobox.launcher.emulator_setup import detector_of, installables
from retrobox.paths import EMULATORS


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture(name="nowhere")
def _nowhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty home and PATH, so only what a test creates is found."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    return tmp_path


def test_app_bin_wins_over_apprun_and_usr_bin(tmp_path: Path) -> None:
    """An explicit binary of app/ beats AppRun, which beats usr/bin."""
    detector = EmulatorBinary("demo", ("demo",))
    _executable(tmp_path / "app" / "usr" / "bin" / "demo")
    apprun = _executable(tmp_path / "app" / "AppRun")
    assert detector.find_in(tmp_path) == apprun
    binary = _executable(tmp_path / "app" / "bin" / "demo")
    assert detector.find_in(tmp_path) == binary


def test_apprun_is_skipped_when_appimages_do_not_count(tmp_path: Path) -> None:
    """A detector for a specific binary ignores AppRun."""
    detector = EmulatorBinary("demo", ("demo-nogui",), appimage=False)
    _executable(tmp_path / "app" / "AppRun")
    assert detector.find_in(tmp_path) is None
    nogui = _executable(tmp_path / "app" / "usr" / "bin" / "demo-nogui")
    assert detector.find_in(tmp_path) == nogui


def test_older_layouts_are_found(tmp_path: Path) -> None:
    """Portable installs and AppImages at the top of the folder are found."""
    detector = EmulatorBinary("demo", ("demo",))
    appimage = _executable(tmp_path / "demo.AppImage")
    assert detector.find_in(tmp_path) == appimage
    portable = _executable(tmp_path / "demo")
    assert detector.find_in(tmp_path) == portable


def test_a_file_that_is_not_executable_does_not_count(tmp_path: Path) -> None:
    """Only executable files count."""
    detector = EmulatorBinary("demo", ("demo",))
    (tmp_path / "app" / "bin").mkdir(parents=True)
    (tmp_path / "app" / "bin" / "demo").write_text("", encoding="utf-8")
    assert detector.find_in(tmp_path) is None


def test_user_appimage_then_path(nowhere: Path) -> None:
    """The user's AppImages come before the distribution's package."""
    detector = EmulatorBinary("demo-not-installed", ("demo",), installer="demo")
    assert detector.find() is None
    on_path = _executable(nowhere / "bin" / "demo")
    assert detector.find() == on_path
    _executable(nowhere / "home" / "Applications" / "Other-1.0.AppImage")
    appimage = _executable(nowhere / "home" / "Applications" / "Demo-2.1-x86_64.AppImage")
    assert detector.find() == appimage


def test_outside_installs_are_ignored_when_not_allowed(nowhere: Path) -> None:
    """outside=False only accepts Retrobox's install."""
    detector = EmulatorBinary("demo-not-installed", ("demo",), outside=False)
    _executable(nowhere / "bin" / "demo")
    assert detector.find() is None


def test_retrobox_install_wins(nowhere: Path) -> None:
    """Retrobox's install beats an install of the distribution."""
    detector = EmulatorBinary("demo-own", ("demo",))
    _executable(nowhere / "bin" / "demo")
    own = _executable(EMULATORS / "demo-own" / "app" / "AppRun")
    try:
        assert detector.find() == own
        assert detector.installed_by_retrobox()
    finally:
        own.unlink()


def test_require_says_how_to_install(nowhere: Path) -> None:
    """The error of a missing emulator names how to install it."""
    del nowhere
    with pytest.raises(RetroboxException, match="retrobox --install-emulator demo"):
        EmulatorBinary("demo-not-installed", ("demo",), installer="demo").require()
    with pytest.raises(RetroboxException, match="package manager"):
        EmulatorBinary("demo-not-installed", ("demo",)).require()


def test_prefix_of(tmp_path: Path) -> None:
    """The prefix of bin/<name> is its parent folder; otherwise its folder."""
    binary = _executable(tmp_path / "prefix" / "bin" / "ares")
    assert EmulatorBinary.prefix_of(binary) == tmp_path / "prefix"
    portable = _executable(tmp_path / "portable" / "redream")
    assert EmulatorBinary.prefix_of(portable) == tmp_path / "portable"


def test_every_installer_has_a_detector() -> None:
    """Every tools/emulators installer maps to the detector of its generator."""
    entries = installables()
    assert {entry.installer for entry in entries} == {
        path.stem for path in (Path(__file__).parents[1] / "tools" / "emulators").glob("*.sh")
    }
    for entry in entries:
        detector = detector_of(entry)
        assert detector is not None, entry
        assert detector.installer == entry.installer, entry
