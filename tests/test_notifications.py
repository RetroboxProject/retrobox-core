"""Desktop notifications: notify-send first, then zenity, then kdialog."""

from __future__ import annotations

from pathlib import Path

import pytest

from retrobox.utils import notifications


def _tool(bin_dir: Path, name: str, status: int, log: Path) -> None:
    script = bin_dir / name
    script.write_text(f'#!/bin/sh\necho "{name} $*" >> {log}\nexit {status}\n', encoding="utf-8")
    script.chmod(0o755)


@pytest.fixture(name="bin_dir")
def fixture_bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A PATH holding only the fake notifiers a test puts there.

    The system folders are left out, so the real notify-send of a desktop
    doesn't answer instead (the fake ones only need /bin/sh, by its path).
    """
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", str(directory))
    return directory


def test_notify_send_first(bin_dir: Path, tmp_path: Path) -> None:
    """notify-send is used when it works, with the summary and the body."""
    log = tmp_path / "calls"
    _tool(bin_dir, "notify-send", 0, log)
    _tool(bin_dir, "zenity", 0, log)
    assert notifications.send_desktop_notification("Title", "Body")
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert calls[0].startswith("notify-send --app-name Retrobox --urgency normal")
    assert calls[0].endswith("Title Body")


def test_falls_back_in_order(bin_dir: Path, tmp_path: Path) -> None:
    """A failing notify-send gives way to zenity (whose 'closed' code 1 counts as shown)."""
    log = tmp_path / "calls"
    _tool(bin_dir, "notify-send", 1, log)
    _tool(bin_dir, "zenity", 1, log)
    _tool(bin_dir, "kdialog", 0, log)
    assert notifications.notify_error("Broken", "details")
    tools = ("notify-send", "zenity", "kdialog")
    calls = [line.split()[0] for line in log.read_text(encoding="utf-8").splitlines()
             if line.startswith(tools)]
    assert calls == ["notify-send", "zenity"]
    assert "--error" in log.read_text(encoding="utf-8")


def test_nothing_available(bin_dir: Path) -> None:
    """Without any notifier it reports failure instead of raising."""
    del bin_dir
    assert not notifications.send_desktop_notification("Title")
