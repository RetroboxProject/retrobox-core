"""Console mode: es_settings.cfg's ShowOnlyExit and ShowExit, from retrobox.ini."""

from __future__ import annotations

from pathlib import Path

from conftest import run_python
from retrobox.utils.es_settings import read_es_settings, write_es_setting

_APPLY = """
from retrobox.paths import ES_SETTINGS_CFG
from retrobox.startup.frontend_conf.console_mode import apply_console_mode
from retrobox.utils.es_settings import read_es_settings
print(apply_console_mode())
settings = read_es_settings(ES_SETTINGS_CFG)
print(settings["ShowOnlyExit"], settings["ShowExit"])
"""


def test_write_replaces_or_adds(tmp_path: Path) -> None:
    """An entry of that name is replaced in place; a new one goes before </config>."""
    path = tmp_path / "es_settings.cfg"
    path.write_text('<?xml version="1.0"?>\n<config>\n\t<bool name="ShowOnlyExit" value="true" />\n'
                    '\t<string name="Language" value="es_ES" />\n</config>\n', encoding="utf-8")
    assert write_es_setting(path, "bool", "ShowOnlyExit", "false")
    assert write_es_setting(path, "bool", "ShowExit", "true")
    assert not write_es_setting(path, "bool", "ShowExit", "true")  # nothing to change
    text = path.read_text(encoding="utf-8")
    assert text.index("ShowOnlyExit") < text.index("Language") < text.index("ShowExit")
    assert text.rstrip().endswith("</config>")
    assert read_es_settings(path) == {
        "ShowOnlyExit": "false", "Language": "es_ES", "ShowExit": "true"}


def test_write_creates_and_keeps_old_files(tmp_path: Path) -> None:
    """A missing file is created; an old one without a root element keeps that shape."""
    new = tmp_path / "new" / "es_settings.cfg"
    assert write_es_setting(new, "bool", "ShowOnlyExit", "false")
    assert read_es_settings(new) == {"ShowOnlyExit": "false"}
    old = tmp_path / "old.cfg"
    old.write_text('<string name="Language" value="en_US" />\n', encoding="utf-8")
    assert write_es_setting(old, "bool", "ShowOnlyExit", "true")
    assert "<config>" not in old.read_text(encoding="utf-8")
    assert read_es_settings(old) == {"Language": "en_US", "ShowOnlyExit": "true"}


def _apply(root: Path) -> list[str]:
    return run_python(root, _APPLY).stdout.splitlines()


def test_retrobox_ini_turns_it_on_and_off(tmp_path: Path) -> None:
    """Off (unset): "Really quit?" and quitting offered; on: the full menu, no quitting."""
    assert _apply(tmp_path) == ["True", "true true"]
    assert _apply(tmp_path) == ["False", "true true"]  # already so

    ini = tmp_path / "home" / ".config" / "retrobox" / "retrobox.ini"
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text("[core]\nconsole_mode = true\n", encoding="utf-8")
    assert _apply(tmp_path) == ["True", "false false"]
    ini.write_text("[core]\nconsole_mode = false\n", encoding="utf-8")
    assert _apply(tmp_path) == ["True", "true true"]
