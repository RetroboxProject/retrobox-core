"""The overlay's input daemon (``retrobox-inputd``), for as long as EmulationStation runs.

The daemon reads every controller and keyboard: it opens Retrobox's overlay
(a controller's hotkey held, Ctrl+Shift+O...) and, while a game runs, maps
its controllers to keys with the game's pad profile (see
``retrobox.launcher.pad_profile``). It comes with ``retrobox-overlay`` (0.5.5
and later).

Where the systemd user manager runs and the overlay's unit is installed
(``retrobox-inputd.service``), the daemon runs as that unit: systemd restarts
it if it crashes, logs it to the journal and, when it stops, takes the
overlay and the mappings' commands with it. The unit is never enabled:
Retrobox starts it here and stops it when EmulationStation ends. It cannot
inherit this process's environment, so it reads it from
``$XDG_RUNTIME_DIR/retrobox/inputd.env``, written just before. Elsewhere
(another init, no user manager) the daemon runs as a child process, as
before.

Either way it is told this process's PID (``RETROBOX_PARENT_PID``,
``--parent``) and stops on its own when it ends, so a Retrobox that crashed
or was killed never leaves it behind.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from retrobox.paths import RUNTIME_DIR

_logger = logging.getLogger(__name__)

DAEMON_COMMAND: Final = "retrobox-inputd"
"""The daemon, in the retrobox-overlay package."""
UNIT: Final = "retrobox-inputd.service"
"""Its systemd user unit."""
ENV_FILE_NAME: Final = "inputd.env"
"""What the unit reads, in $XDG_RUNTIME_DIR/retrobox (``%t/retrobox``)."""
PARENT_VARIABLE: Final = "RETROBOX_PARENT_PID"

_NO_STDIO: Final = {
    "stdin": subprocess.DEVNULL,
    "stdout": subprocess.DEVNULL,
    "stderr": subprocess.DEVNULL,
}
_SYSTEMCTL_TIMEOUT_S: Final = 10.0
_STOP_TIMEOUT_S: Final = 3.0

# What systemd sets for a process of its own, and what only makes sense in
# this process: never passed on to the unit.
_NOT_PASSED: Final = frozenset({
    "INVOCATION_ID", "JOURNAL_STREAM", "LISTEN_FDNAMES", "LISTEN_FDS", "LISTEN_PID",
    "MANAGERPID", "NOTIFY_SOCKET", "SYSTEMD_EXEC_PID", "WATCHDOG_PID", "WATCHDOG_USEC",
    "OLDPWD", "PWD", "SHLVL", "_",
})


@dataclass
class InputDaemon:
    """The running daemon: the systemd unit, or a child process."""

    process: subprocess.Popen[bytes] | None = None
    env_file: Path | None = None

    def stop(self) -> None:
        """Stop it (and the overlay, if it is open)."""
        if self.env_file is not None:
            _systemctl("stop", UNIT)
            self.env_file.unlink(missing_ok=True)
            return
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=_STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def _systemctl(*args: str) -> subprocess.CompletedProcess[str] | None:
    """Run ``systemctl --user`` with these arguments; None if it could not run."""
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return None
    try:
        return subprocess.run(
            [systemctl, "--user", *args],
            capture_output=True,
            text=True,
            timeout=_SYSTEMCTL_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        _logger.warning("systemctl --user %s: %s", " ".join(args), err)
        return None


def _unit_env_file() -> Path | None:
    """Where the unit reads its environment, if the unit can be used at all.

    It needs systemd as the init (``/run/systemd/system``), a user manager
    this process can reach, the unit installed and ``$XDG_RUNTIME_DIR`` (the
    unit's ``%t``).
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if not runtime or not Path("/run/systemd/system").is_dir():
        return None
    result = _systemctl("show", "--property=LoadState", "--value", UNIT)
    if result is None or result.returncode != 0 or result.stdout.strip() != "loaded":
        _logger.info("%s is not available: the input daemon runs as a child", UNIT)
        return None
    return Path(runtime) / "retrobox" / ENV_FILE_NAME


def _quoted(value: str) -> str:
    """A value for a systemd environment file: double quotes, \\ " ` $ escaped."""
    escaped = "".join(f"\\{char}" if char in '\\"`$' else char for char in value)
    return f'"{escaped}"'


def env_file_text(env: dict[str, str]) -> str:
    """The environment as a systemd environment file (EnvironmentFile=).

    A variable systemd sets itself, or whose name or value cannot be written
    there (a newline in it), is left out.
    """
    lines = [
        f"{name}={_quoted(value)}"
        for name, value in sorted(env.items())
        if name not in _NOT_PASSED
        and name.replace("_", "a").isalnum()
        and not name[0].isdigit()
        and "\n" not in value
    ]
    return "".join(f"{line}\n" for line in lines)


def start_input_daemon(env: dict[str, str]) -> InputDaemon | None:
    """Start the input daemon with EmulationStation's environment, if it is installed."""
    daemon = shutil.which(DAEMON_COMMAND)
    if daemon is None:
        _logger.warning(
            "%s is not installed (retrobox-overlay 0.5.5 or later): no overlay, "
            "no controller hotkeys", DAEMON_COMMAND,
        )
        return None
    env = {**env, PARENT_VARIABLE: str(os.getpid()), "RETROBOX_RUNTIME_DIR": str(RUNTIME_DIR)}
    env_file = _unit_env_file()
    if env_file is not None:
        started = _start_unit(env, env_file)
        if started is not None:
            return started
    try:
        # its own session, its output nowhere (it logs to its own file)
        # pylint: disable-next=consider-using-with  # stopped by InputDaemon.stop()
        process = subprocess.Popen(
            [daemon, "--parent", str(os.getpid())],
            env=env,
            start_new_session=True,
            **_NO_STDIO,
        )
    except OSError as err:
        _logger.warning("cannot start %s: %s", DAEMON_COMMAND, err)
        return None
    _logger.info("Input daemon started (pid %d)", process.pid)
    return InputDaemon(process=process)


def _start_unit(env: dict[str, str], env_file: Path) -> InputDaemon | None:
    """Start the unit with this environment; None if it did not start."""
    try:
        env_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = env_file.with_suffix(".tmp")
        temporary.write_text(env_file_text(env), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(env_file)
    except OSError as err:
        _logger.warning("cannot write %s: %s", env_file, err)
        return None
    # restart: a unit left running (it should not be) takes this environment too
    result = _systemctl("restart", UNIT)
    if result is None or result.returncode != 0:
        _logger.warning(
            "cannot start %s: %s", UNIT, result.stderr.strip() if result else "systemctl failed"
        )
        env_file.unlink(missing_ok=True)
        return None
    _logger.info("Input daemon started (%s)", UNIT)
    return InputDaemon(env_file=env_file)


def stop_input_daemon(daemon: InputDaemon | None) -> None:
    """Stop the input daemon, if it was started."""
    if daemon is not None:
        daemon.stop()
