"""Keeping the computer awake while a game runs."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from conftest import LIB_DIR
from retrobox.launcher import idle_inhibit

HELPERS = Path(__file__).resolve().parent / "helpers"


def _holders(pid: int) -> list[str]:
    """The pids of the processes that hold logind's lock for ``pid``."""
    result = subprocess.run(
        ["pgrep", "-f", f"tail --pid={pid} "], capture_output=True, text=True, check=False
    )
    return result.stdout.split()


@pytest.fixture(name="fake_inhibit")
def fixture_fake_inhibit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A systemd-inhibit that logs its arguments and runs the command it is given."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "inhibit.log"
    script = bin_dir / "systemd-inhibit"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            echo "$*" >> {log}
            while [ "${{1#--}}" != "$1" ]; do shift; done
            exec "$@"
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    return log


def test_logind_lock_is_held_and_released(fake_inhibit: Path) -> None:
    """The lock is taken with the right arguments, held during the block and released."""
    with idle_inhibit.inhibit_idle("Playing Test"):
        assert len(_holders(os.getpid())) == 1
    assert _holders(os.getpid()) == []
    arguments = fake_inhibit.read_text(encoding="utf-8")
    assert "--what=idle:sleep" in arguments
    assert "--who=Retrobox" in arguments
    assert "--why=Playing Test" in arguments
    assert "--mode=block" in arguments


def test_lock_released_when_the_body_raises(fake_inhibit: Path) -> None:
    """An exception inside the block still releases the lock."""
    del fake_inhibit
    with pytest.raises(RuntimeError):
        with idle_inhibit.inhibit_idle("Playing Test"):
            raise RuntimeError("the emulator crashed")
    assert _holders(os.getpid()) == []


def test_lock_released_when_the_launcher_dies(fake_inhibit: Path, tmp_path: Path) -> None:
    """Killing the launcher outright (SIGKILL) still releases the lock."""
    del fake_inhibit
    child = subprocess.Popen(  # pylint: disable=consider-using-with
        [
            sys.executable,
            "-c",
            "import time\n"
            "from retrobox.launcher.idle_inhibit import inhibit_idle\n"
            "with inhibit_idle('x'):\n"
            "    print('held', flush=True)\n"
            "    time.sleep(60)\n",
        ],
        env={**os.environ, "PYTHONPATH": str(LIB_DIR)},
        stdout=subprocess.PIPE,
        text=True,
        cwd=tmp_path,
    )
    assert child.stdout is not None and child.stdout.readline().strip() == "held"
    assert len(_holders(child.pid)) == 1
    child.kill()
    child.wait()
    deadline = time.monotonic() + 5
    while _holders(child.pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert _holders(child.pid) == []


def test_refused_lock_does_not_stop_the_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When logind refuses, the block still runs and the log says why."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "systemd-inhibit"
    script.write_text("#!/bin/sh\necho 'Access denied' >&2\nexit 1\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)

    ran = False
    with idle_inhibit.inhibit_idle("Playing Test"):
        ran = True
    assert ran
    assert "Access denied" in caplog.text


def test_no_inhibit_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without systemd-inhibit or elogind-inhibit, nothing is held and nothing fails."""
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    with idle_inhibit.inhibit_idle("Playing Test"):
        pass


@pytest.mark.skipif(
    shutil.which("dbus-run-session") is None or importlib.util.find_spec("jeepney") is None,
    reason="needs dbus-run-session and jeepney",
)
def test_screensaver_inhibitor(tmp_path: Path) -> None:
    """Inhibit is called with Retrobox and the reason, and UnInhibit with its cookie."""
    calls = tmp_path / "calls.log"
    script = textwrap.dedent(
        f"""\
        {sys.executable} {HELPERS / 'fake_screensaver.py'} > {calls} &
        service=$!
        until grep -q ready {calls} 2>/dev/null; do sleep 0.05; done
        PATH=/nonexistent {sys.executable} -c '
        from retrobox.launcher.idle_inhibit import inhibit_idle
        with inhibit_idle("Playing Test"):
            pass
        '
        sleep 0.2
        kill "$service" 2>/dev/null || true
        """
    )
    subprocess.run(
        ["dbus-run-session", "--", "sh", "-c", script],
        env={**os.environ, "PYTHONPATH": str(LIB_DIR)},
        check=True,
        timeout=30,
        cwd=tmp_path,
    )
    lines = calls.read_text(encoding="utf-8").splitlines()
    assert lines == ["ready", "Inhibit Retrobox Playing Test", "UnInhibit 42"]
