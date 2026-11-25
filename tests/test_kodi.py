"""Kodi: where it is found (its Flatpak counts) and the add-ons enabled with it."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from retrobox.configgen.generators.kodi import kodi_addons, kodi_paths
from retrobox.configgen.generators.kodi.kodi_paths import FLATPAK_MARKER, KodiBinary


def _fake_flatpak(bin_dir: Path, installed: bool) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    flatpak = bin_dir / "flatpak"
    flatpak.write_text(f"#!/bin/sh\nexit {0 if installed else 1}\n", encoding="utf-8")
    flatpak.chmod(0o755)


@pytest.fixture(name="kodi")
def _kodi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> KodiBinary:
    """Kodi's detector over an empty emulators folder, home and PATH."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    (tmp_path / "bin").mkdir()
    monkeypatch.setattr(KodiBinary, "directory", property(lambda self: tmp_path / "kodi"))
    return KodiBinary(folder="kodi", names=("kodi",), installer="kodi", appimage=False)


def test_kodi_is_missing_without_flatpak_or_build(kodi: KodiBinary) -> None:
    """No build, no Flatpak, no package: Kodi is missing (offered)."""
    assert kodi.find() is None


def test_any_kodi_flatpak_counts(kodi: KodiBinary, tmp_path: Path) -> None:
    """A Kodi Flatpak, whoever installed it, is Kodi installed."""
    _fake_flatpak(tmp_path / "bin", installed=True)
    assert kodi.find() == tmp_path / "bin" / "flatpak"


def test_the_marker_counts_only_with_its_flatpak(kodi: KodiBinary, tmp_path: Path) -> None:
    """Retrobox's marker only counts while its Flatpak is installed."""
    marker = tmp_path / "kodi" / "app" / FLATPAK_MARKER
    marker.parent.mkdir(parents=True)
    marker.write_text("tv.kodi.Kodi\n", encoding="utf-8")
    _fake_flatpak(tmp_path / "bin", installed=False)
    assert kodi.find_in(tmp_path / "kodi") is None
    _fake_flatpak(tmp_path / "bin", installed=True)
    assert kodi.find_in(tmp_path / "kodi") == marker


def test_a_build_wins(kodi: KodiBinary, tmp_path: Path) -> None:
    """Retrobox's build is preferred over a Flatpak."""
    binary = tmp_path / "kodi" / "app" / "bin" / "kodi"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    _fake_flatpak(tmp_path / "bin", installed=True)
    assert kodi.find() == binary


def test_the_detector_is_kodis() -> None:
    """The emulator setup finds Kodi's installer and no AppImages."""
    assert kodi_paths.KODI.installer == "kodi"
    assert not kodi_paths.KODI.appimage


def _database(userdata: Path, rows: list[tuple[str, int]]) -> Path:
    database = userdata / "Database" / "Addons33.db"
    database.parent.mkdir(parents=True)
    (userdata / "Database" / "Addons27.db").write_text("", encoding="utf-8")  # an older one
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE installed (id INTEGER PRIMARY KEY, addonID TEXT UNIQUE, "
            "enabled BOOLEAN, installDate TEXT, lastUpdated TEXT, lastUsed TEXT, "
            "origin TEXT NOT NULL DEFAULT '', disabledReason INTEGER NOT NULL DEFAULT 0)"
        )
        connection.executemany("INSERT INTO installed (addonID, enabled) VALUES (?, ?)", rows)
    return database


def _enabled(database: Path) -> dict[str, int]:
    with sqlite3.connect(database) as connection:
        return dict(connection.execute("SELECT addonID, enabled FROM installed"))


def test_the_webapp_launcher_is_enabled(tmp_path: Path) -> None:
    """The WebApp Launcher is enabled in the newest database; others are left alone."""
    userdata = tmp_path / "userdata"
    (tmp_path / "addons" / "plugin.program.webapplauncher").mkdir(parents=True)
    database = _database(userdata, [("plugin.program.webapplauncher", 0), ("other", 0)])
    assert kodi_addons.enable_addons(userdata) == ["plugin.program.webapplauncher"]
    assert _enabled(database) == {"plugin.program.webapplauncher": 1, "other": 0}


def test_a_new_addon_gets_a_row(tmp_path: Path) -> None:
    """An add-on Kodi has not listed yet gets an enabled row."""
    userdata = tmp_path / "userdata"
    (tmp_path / "addons" / "plugin.program.webapplauncher").mkdir(parents=True)
    database = _database(userdata, [])
    assert kodi_addons.enable_addons(userdata) == ["plugin.program.webapplauncher"]
    assert _enabled(database) == {"plugin.program.webapplauncher": 1}


def test_nothing_without_the_addon_or_a_database(tmp_path: Path) -> None:
    """Nothing changes before Kodi's first start or without the add-on."""
    userdata = tmp_path / "userdata"
    userdata.mkdir()
    (tmp_path / "addons" / "plugin.program.webapplauncher").mkdir(parents=True)
    assert not kodi_addons.enable_addons(userdata)  # Kodi never started
    (tmp_path / "addons" / "plugin.program.webapplauncher").rmdir()
    database = _database(userdata, [("plugin.program.webapplauncher", 0)])
    assert not kodi_addons.enable_addons(userdata)  # not installed by kodi.sh
    assert _enabled(database) == {"plugin.program.webapplauncher": 0}
