"""``retrobox --doctor``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import run_retrobox_module
from retrobox import doctor


def _es_settings(root: Path, **values: str) -> None:
    """Write an es_settings.cfg (EmulationStation's XML form) in a sandbox."""
    folder = root / "home" / ".config" / "retrobox" / "frontend" / ".emulationstation"
    folder.mkdir(parents=True, exist_ok=True)
    entries = "\n".join(
        f'  <string name="global.{key.replace("__", ".")}" value="{value}" />'
        for key, value in values.items()
    )
    (folder / "es_settings.cfg").write_text(
        f'<?xml version="1.0"?>\n<config>\n{entries}\n</config>\n', encoding="utf-8"
    )


def _report(root: Path) -> dict:
    result = run_retrobox_module(root, "retrobox.doctor", "--json", check=False)
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def _find(report: dict, section: str, name: str) -> dict:
    return next(
        check for check in report["checks"]
        if check["section"] == section and check["name"] == name
    )


def test_every_section_reports(tmp_path: Path) -> None:
    """The report covers every area, and each check has a known status."""
    report = _report(tmp_path)
    sections = {check["section"] for check in report["checks"]}
    assert sections == {
        "Retrobox", "Components", "Display", "Input", "Power", "Folders", "Emulators",
        "RetroAchievements",
    }
    assert {check["status"] for check in report["checks"]} <= {"OK", "INFO", "WARN", "ERR"}


def test_errors_set_the_exit_status(tmp_path: Path) -> None:
    """No EmulationStation in the sandbox: an error, and exit status 1."""
    result = run_retrobox_module(tmp_path, "retrobox.doctor", check=False)
    assert result.returncode == 1
    assert "[ERR ] EmulationStation" in result.stdout
    assert "-> install retrobox-emulationstation" in result.stdout


def test_missing_roms_folder_is_an_error(tmp_path: Path) -> None:
    """A roms_dir that doesn't exist (autocorrect off) is reported."""
    ini = tmp_path / "home" / ".config" / "retrobox" / "retrobox.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text(
        f"[core]\nautocorrect_paths = false\n[paths]\nroms_dir = {tmp_path / 'gone'}\n",
        encoding="utf-8",
    )
    assert _find(_report(tmp_path), "Folders", "ROMs")["status"] == "ERR"


def test_secrets_are_never_printed(tmp_path: Path) -> None:
    """The account shows its user and whether a token is set, never the token."""
    _es_settings(
        tmp_path,
        retroachievements="1",
        retroachievements__username="player",
        retroachievements__token="SECRET-TOKEN",
    )
    result = run_retrobox_module(tmp_path, "retrobox.doctor", "--json", check=False)
    assert "SECRET-TOKEN" not in result.stdout
    account = _find(json.loads(result.stdout), "RetroAchievements", "Account")
    assert account["status"] == "OK"
    assert account["detail"] == "player, with a token"


def test_password_without_token_warns(tmp_path: Path) -> None:
    """A password alone works, but costs a login per standalone-emulator game."""
    _es_settings(
        tmp_path,
        retroachievements="1",
        retroachievements__username="player",
        retroachievements__password="hunter2",
    )
    result = run_retrobox_module(tmp_path, "retrobox.doctor", "--json", check=False)
    assert "hunter2" not in result.stdout
    assert _find(json.loads(result.stdout), "RetroAchievements", "Account")["status"] == "WARN"


def test_a_crashing_check_does_not_stop_the_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    """A check that raises is reported as an error; the others still run."""

    def broken():
        raise RuntimeError("boom")
        yield  # pylint: disable=unreachable

    monkeypatch.setattr(doctor, "CHECKS", (broken, doctor.check_power))
    results = doctor.run_checks()
    assert results[0].status is doctor.Status.ERROR
    assert "boom" in results[0].detail
    assert any(result.section == "Power" for result in results)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0.6.1", (0, 6, 1)), ("0.5.5-rc1", (0, 5, 5)), ("v1", (1,)), ("2.0.x", (2, 0)), ("", ())],
)
def test_version_tuple(text: str, expected: tuple[int, ...]) -> None:
    """Versions compare by their numbers."""
    assert doctor._version_tuple(text) == expected  # pylint: disable=protected-access


def test_text_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """The text report groups by section, shows hints for problems only, and counts them."""
    results = [
        doctor.Check("A", "one", doctor.Status.OK, "fine", "never shown"),
        doctor.Check("A", "two", doctor.Status.WARN, "meh", "do this"),
        doctor.Check("B", "three", doctor.Status.ERROR, "bad", "do that"),
    ]
    monkeypatch.setattr(doctor, "retrobox_version", lambda: "test")
    text = doctor.format_text(results, color=False)
    assert "never shown" not in text
    assert "-> do this" in text and "-> do that" in text
    assert text.endswith("1 error(s), 1 warning(s)")
    assert "\033[" not in text
