"""The Kodi launcher: no game session, the install screen, and what Kodi leaves behind."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from retrobox.configgen.exceptions import RetroboxException
from retrobox.configgen.generators import get_generator
from retrobox.launcher import kodi_launch, launch_phase
from retrobox.launcher.cli import build_argument_parser

if TYPE_CHECKING:
    from retrobox.configgen.Command import Command


@dataclass
class _Calls:
    """What the launcher did, in order."""

    frontend: Path
    events: list[str] = field(default_factory=list)
    command: Command | None = None
    on_started: object = "unset"
    frontend_while_running: bool = False


@pytest.fixture(name="calls")
def _calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Calls:
    calls = _Calls(tmp_path / "frontend.json")
    userdata = tmp_path / "userdata"

    monkeypatch.setattr(kodi_launch, "reinstall_requested", lambda: False)
    monkeypatch.setattr(kodi_launch.Controller, "load_for_players", lambda *_: [])
    monkeypatch.setattr(kodi_launch.kodiConfig, "kodi_userdata", lambda: userdata)
    monkeypatch.setattr(
        kodi_launch.kodiConfig, "write_kodi_config", lambda *_: calls.events.append("config")
    )
    monkeypatch.setattr(
        kodi_launch.kodi_addons, "enable_addons", lambda *_: calls.events.append("addons")
    )
    monkeypatch.setattr(
        kodi_launch, "start_frontend", lambda: launch_phase.start_frontend(calls.frontend)
    )
    monkeypatch.setattr(
        kodi_launch, "end_frontend", lambda: launch_phase.end_frontend(calls.frontend)
    )

    def run_command(command: Command, on_started: object = None) -> int:
        calls.events.append("run")
        calls.command = command
        calls.on_started = on_started
        calls.frontend_while_running = calls.frontend.is_file()
        return 0

    monkeypatch.setattr(kodi_launch, "run_command", run_command)
    return calls


def _args() -> object:
    return build_argument_parser(require_game=False).parse_args([])


def test_kodi_runs_without_a_game_session(calls: _Calls, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured, then run with no session callback; the frontend file is there meanwhile."""
    monkeypatch.setattr(kodi_launch, "ensure_emulator", lambda *_, **__: True)
    assert kodi_launch.run(_args()) == 0  # type: ignore[arg-type]
    assert calls.events == ["config", "addons", "run"]
    assert calls.command is not None
    assert Path(calls.command.array[0]).name == "retrobox-kodi"
    assert calls.on_started is None  # no session.json is published
    assert calls.frontend_while_running
    assert not calls.frontend.exists()  # and it is gone afterwards


def test_the_frontend_file_goes_when_kodi_fails(
    calls: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash of the launcher around Kodi does not leave the overlay off."""
    monkeypatch.setattr(kodi_launch, "ensure_emulator", lambda *_, **__: True)

    def boom(*_: object, **__: object) -> int:
        raise RetroboxException("boom")

    monkeypatch.setattr(kodi_launch, "run_command", boom)
    with pytest.raises(RetroboxException):
        kodi_launch.run(_args())  # type: ignore[arg-type]
    assert not calls.frontend.exists()


def test_declining_the_install_goes_back(calls: _Calls, monkeypatch: pytest.MonkeyPatch) -> None:
    """Declined (or failed) installation: nothing is written or run."""
    monkeypatch.setattr(kodi_launch, "ensure_emulator", lambda *_, **__: False)
    assert kodi_launch.run(_args()) == 0  # type: ignore[arg-type]
    assert not calls.events


@pytest.mark.parametrize("held", [False, True])
def test_the_update_chord_is_read_first(
    calls: _Calls, monkeypatch: pytest.MonkeyPatch, held: bool
) -> None:
    """L1+R1 held asks for the install screen to update Kodi."""
    asked: list[tuple[str, bool]] = []
    monkeypatch.setattr(kodi_launch, "reinstall_requested", lambda: held)
    monkeypatch.setattr(
        kodi_launch,
        "ensure_emulator",
        lambda emulator, reinstall=False: asked.append((emulator, reinstall)) or True,
    )
    kodi_launch.run(_args())  # type: ignore[arg-type]
    assert asked == [("kodi", held)]
    assert calls.events[-1] == "run"


def test_the_command_line_has_no_game() -> None:
    """EmulationStation's Kodi entry passes the controllers and no -system or -rom."""
    args = build_argument_parser(require_game=False).parse_args(["-p1index", "0"])
    assert args.p1index == 0
    assert args.rom is None
    with pytest.raises(SystemExit):
        build_argument_parser().parse_args(["-p1index", "0"])


def test_the_frontend_file_names_its_process(tmp_path: Path) -> None:
    """``frontend.json`` carries the pid and start time the overlay checks."""
    path = tmp_path / "frontend.json"
    launch_phase.start_frontend(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == launch_phase.LAUNCH_VERSION
    assert data["pid"] > 0
    assert "phase" not in data
    launch_phase.end_frontend(path)
    assert not path.exists()


def test_a_frontend_file_of_another_process_stays(tmp_path: Path) -> None:
    """Only the process that wrote it removes it."""
    path = tmp_path / "frontend.json"
    path.write_text('{"version": 1, "pid": 1}', encoding="utf-8")
    launch_phase.end_frontend(path)
    assert path.exists()


def test_kodi_is_not_a_game_any_more() -> None:
    """No generator for Kodi: it is not started by retrobox-launch."""
    with pytest.raises(RetroboxException):
        get_generator("kodi", "kodi")
