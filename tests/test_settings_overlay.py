"""The settings window's overlay page: overlay.ini through the same model."""

from __future__ import annotations

from pathlib import Path

import yaml

from retrobox.settings.model import SettingsModel
from retrobox.settings.schema import OVERLAY_INI, PAGES, Kind, Limits, ini_files, setting_by_id

I18N = Path(__file__).parents[1] / "lib/retrobox/settingsui/i18n/en.yaml"


def _model(tmp_path: Path, system: str = "", user: str = "") -> SettingsModel:
    etc, config = tmp_path / "etc", tmp_path / "config"
    etc.mkdir()
    config.mkdir()
    if system:
        (etc / OVERLAY_INI).write_text(system, encoding="utf-8")
    if user:
        (config / OVERLAY_INI).write_text(user, encoding="utf-8")
    return SettingsModel(etc, config, ini=OVERLAY_INI)


def test_the_overlay_page_edits_overlay_ini() -> None:
    """Its page is the overlay's file, and shows only with the overlay installed."""
    overlay = next(page for page in PAGES if page.id == "overlay")
    assert (overlay.ini, overlay.requires) == (OVERLAY_INI, "retrobox-overlay")
    assert ini_files() == ("retrobox.ini", OVERLAY_INI)


def test_values_layer_and_save_to_the_user_file(tmp_path: Path) -> None:
    """System-wide values are inherited; changes go to the user's overlay.ini only."""
    model = _model(tmp_path, system="[sounds]\nvolume = 30\n", user="[clock]\nsize = small\n")
    volume, size = setting_by_id("sounds.volume"), setting_by_id("clock.size")
    assert model.inherited(volume) == "30"
    assert model.value(size) == "small"
    model.set(volume, "80")
    model.apply()
    text = (tmp_path / "config" / OVERLAY_INI).read_text(encoding="utf-8")
    assert "volume = 80" in text
    assert "size = small" in text
    assert not (tmp_path / "config" / "retrobox.ini").exists()


def test_the_same_value_written_otherwise_is_no_change(tmp_path: Path) -> None:
    """``1.00`` is the default ``1``, ``ffffffff`` the default ``FFFFFFFF``."""
    model = _model(tmp_path)
    model.set(setting_by_id("touch.row_scale"), "1.00")
    model.set(setting_by_id("clock.color"), "ffffffff")
    model.set(setting_by_id("overlay.animation_ms"), "150")
    assert not model.dirty


def test_no_drop_ins_for_the_overlay(tmp_path: Path) -> None:
    """The overlay reads no overlay.ini.d: nothing there locks a setting."""
    model = _model(tmp_path)
    dropins = tmp_path / "config" / f"{OVERLAY_INI}.d"
    dropins.mkdir()
    (dropins / "x.ini").write_text("[sounds]\nvolume = 10\n", encoding="utf-8")
    model = SettingsModel(tmp_path / "etc", tmp_path / "config", ini=OVERLAY_INI)
    assert model.locked_by(setting_by_id("sounds.volume")) is None


def test_numbers_have_limits_and_every_setting_a_label() -> None:
    """Every number has a range; every setting, page and group a text in English."""
    texts = yaml.safe_load(I18N.read_text(encoding="utf-8"))
    for page in PAGES:
        assert f"page.{page.id}" in texts
        for group in page.groups:
            assert f"group.{group.id}" in texts
            for setting in group.settings:
                assert setting.id in texts, setting.id
                if setting.kind in (Kind.INTEGER, Kind.DECIMAL):
                    assert setting.limits is not None, setting.id
                for choice in setting.choices:
                    assert f"choice.{choice}" in texts, choice
    assert Limits(0, 1, 0.05).decimals == 2
    assert Limits(0, 100, 5).decimals == 0
