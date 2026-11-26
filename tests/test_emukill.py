"""Ending the game: the windows are asked to close first, the signals come after."""

from __future__ import annotations

import pytest

from retrobox.launcher import emukill
from retrobox.launcher.game_state import GameState

LISTING = """\
0x01200003  0 4242   pc Dolphin
0x01400007  0 4243   pc Dolphin | Game
0x01600001  0 0      pc EmulationStation
0x01800002 -1 9999   pc other
"""


def _state() -> GameState:
    return GameState(
        pid=4242, pgid=4242, start_time=1, launcher_pid=1, system="gc",
        emulator="dolphin", core="", rom="game.iso",
    )


def test_windows_of_picks_those_of_the_game() -> None:
    """Only the windows of the game's processes; a window of no process is left alone."""
    assert emukill.windows_of(LISTING, {4242, 4243}) == ["0x01200003", "0x01400007"]
    assert not emukill.windows_of(LISTING, {1})
    assert not emukill.windows_of("", {4242})


@pytest.fixture(name="signals")
def _signals(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the signal stages with a record of whether they ran."""
    ran: list[str] = []
    monkeypatch.setattr(emukill, "_end_env_processes", lambda *_: ran.append("env"))
    monkeypatch.setattr(emukill, "_end_process_group", lambda *_: ran.append("group"))
    return ran


def test_a_game_that_quits_on_its_own_gets_no_signal(
    monkeypatch: pytest.MonkeyPatch, signals: list[str]
) -> None:
    """The window is asked to close and the game is gone before the grace ends."""
    monkeypatch.setattr(emukill, "ask_windows_to_close", lambda _state: 1)
    monkeypatch.setattr(emukill, "_game_gone", lambda _state: True)
    emukill.end_game(_state())
    assert not signals


def test_a_game_that_does_not_quit_gets_the_signals(
    monkeypatch: pytest.MonkeyPatch, signals: list[str]
) -> None:
    """After the grace the signals go, as they always did."""
    monkeypatch.setattr(emukill, "CLOSE_GRACE", 0.2)
    monkeypatch.setattr(emukill, "ask_windows_to_close", lambda _state: 1)
    monkeypatch.setattr(emukill, "_game_gone", lambda _state: False)
    emukill.end_game(_state())
    assert signals == ["env", "group"]


def test_with_no_window_to_close_the_signals_go_at_once(
    monkeypatch: pytest.MonkeyPatch, signals: list[str]
) -> None:
    """Nothing was asked (no window tool, no window): no waiting."""
    monkeypatch.setattr(emukill, "ask_windows_to_close", lambda _state: 0)
    monkeypatch.setattr(emukill, "_game_gone", lambda _state: pytest.fail("it waited"))
    emukill.end_game(_state())
    assert signals == ["env", "group"]


def test_a_failing_window_tool_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool that cannot start (or hangs) means no request, never an exception."""
    def broken(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("wmctrl")

    monkeypatch.setattr(emukill.subprocess, "run", broken)
    assert emukill.ask_windows_to_close(_state()) == 0
