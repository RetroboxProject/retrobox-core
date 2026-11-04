"""Running of the emulator command and handling of its exit status."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from retrobox.configgen.exceptions import BadCommandLineArguments, UnexpectedEmulatorExit
from retrobox.paths import RUNTIME_DIR

if TYPE_CHECKING:
    from types import FrameType

    from retrobox.configgen.Command import Command

_logger = logging.getLogger(__name__)

_ENV_DUMP_FILE = RUNTIME_DIR / "env-launcher.txt"

_KILL_AFTER_SECONDS = 10
"""Seconds the emulator has to quit once the launcher is asked to stop."""


@dataclass
class _RunningProcess:
    """The emulator process currently running, so signals can kill it."""

    proc: subprocess.Popen[bytes] | None = None


_running = _RunningProcess()


def _build_environment(command: Command) -> dict[str, str | Path]:
    """Compute the child environment: os.environ overridden by the command's.

    A None value in command.env means "unset this variable, even if it's
    currently inherited from the parent environment" -- e.g. to defeat a
    login-session default such as RETROBOX_MANGOHUD_DISABLE=1. The result is
    a fresh dict rather than something stored back on `command`, since
    subprocess.Popen (and Command itself) only understand str/Path values,
    never None.
    """
    envvars: dict[str, str | Path] = dict(os.environ)
    for key, value in command.env.items():
        if value is None:
            envvars.pop(key, None)
        else:
            envvars[key] = value
    return envvars


def run_command(
    command: Command, on_started: Callable[[subprocess.Popen[bytes]], None] | None = None
) -> int:
    """Run the generated command with subprocess.Popen.

    The emulator runs in a session (and process group) of its own, so that
    ``retrobox-emukill`` can signal its whole tree without reaching the
    launcher or the frontend. ``on_started`` is called with the process as
    soon as it exists.

    Also handles error codes and exceptions to send them to the launcher.

    Returns:
        The exit code of the emulator process.

    Raises:
        BadCommandLineArguments: If the command is empty.
        UnexpectedEmulatorExit: If running the emulator failed unexpectedly.
    """
    envvars = _build_environment(command)

    _logger.info("command: %s", command.array)
    _logger.debug("env: %s", envvars)

    if not command.array:
        raise BadCommandLineArguments

    with _ENV_DUMP_FILE.open("w", encoding="utf-8") as env_file:
        for key, value in sorted(envvars.items()):
            print(f"{key}={value}", file=env_file)

    exitcode = 0

    try:
        with subprocess.Popen(
            command.array,
            env=envvars,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            _running.proc = process
            if on_started is not None:
                on_started(process)
            out, err = process.communicate()
            exitcode = process.returncode

            if err is not None:
                _logger.error(err.decode(errors="backslashreplace"))

            if out is not None:
                _logger.debug(out.decode(errors="backslashreplace"))

    except BrokenPipeError:
        pass
    except BaseException as err:
        _logger.error("emulator exited: %s: %s", type(err).__name__, err)
        raise UnexpectedEmulatorExit from err

    return exitcode


@dataclass
class _Interrupts:
    """How many times the launcher has been asked to stop."""

    count: int = 0


_interrupts = _Interrupts()


def _on_interrupt(sig: int, _frame: FrameType | None) -> None:
    """Stop the emulator's process group when the launcher is interrupted.

    The emulator no longer shares the launcher's process group, so a Ctrl+C
    or the end of the session does not reach it by itself. The first signal
    asks it to quit (SIGTERM); a second one, or the alarm set by the first
    one, kills it.
    """
    _logger.debug("Exiting (signal %s)", sig)
    _interrupts.count += 1
    proc = _running.proc
    if proc is None or proc.poll() is not None:
        return
    kill_signal = signal.Signals.SIGTERM if _interrupts.count == 1 else signal.Signals.SIGKILL
    if kill_signal is signal.Signals.SIGTERM:
        signal.alarm(_KILL_AFTER_SECONDS)
    _logger.debug("sending %s to the emulator's process group", kill_signal.name)
    try:
        os.killpg(proc.pid, kill_signal)
    except ProcessLookupError:
        pass


def install_interrupt_handler() -> None:
    """Forget any previous process and stop the emulator on SIGINT, SIGTERM or SIGHUP."""
    _running.proc = None
    _interrupts.count = 0
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
        signal.signal(sig, _on_interrupt)


def normalize_exit_code(exitcode: int) -> int:
    """Map an exit code caused by a signal (negative value) to a clean exit."""
    if exitcode >= 0:
        return exitcode

    signal_number = -exitcode
    if signal_number >= signal.NSIG:
        return exitcode

    signal_description = signal.strsignal(signal_number)
    if signal_description and ":" not in signal_description:
        signal_description = f"{signal_description}: {signal_number}"

    _logger.debug("Emulator terminated by signal (%s)", signal_description)
    return 0
