"""The installer child process, run in a pseudo-terminal.

The installer gets a real terminal (a pty), so whatever asks the user
something (sudo's password prompt, a git credential...) works as in any
terminal emulator: the screen writes the keys to the pty and shows what comes
back, echo included. ``setsid --ctty`` makes the pty the controlling terminal
of the installer, which sudo needs to read the password from ``/dev/tty``.

A background thread blocks on the pty (no polling), copies everything to a
log file and hands the text to the UI through
:meth:`InstallerProcess.take_output`. The UI is woken up through ``notify``,
at most once until it takes what is pending, so a chatty installer (a
compiler, say) cannot flood the event queue.
"""

from __future__ import annotations

import codecs
import contextlib
import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import termios
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

_READ_SIZE = 65536
# no colors or cursor tricks: the terminal box only understands plain text;
# apt's debconf questions cannot be drawn either, so they take their defaults
_ENVIRONMENT = {
    "NO_COLOR": "1",
    "TERM": "dumb",
    "PYTHONUNBUFFERED": "1",
    "DEBIAN_FRONTEND": "noninteractive",
}


def _set_window_size(fd: int, columns: int, rows: int) -> None:
    """Tell the pty its size (the kernel sends SIGWINCH to the installer)."""
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))


class InstallerProcess:
    """Runs one installer command in a pty and collects its output."""

    def __init__(self, notify: Callable[[], None]) -> None:
        self._notify = notify
        self._lock = threading.Lock()
        self._pending: list[str] = []
        self._woken = False
        self._process: subprocess.Popen[bytes] | None = None
        self._master = -1
        self.returncode: int | None = None

    def start(self, command: Sequence[str], log_path: Path, size: tuple[int, int]) -> None:
        """Start ``command`` in a ``size`` (columns, rows) pty, saving its output to ``log_path``.

        Raises OSError if it cannot be run.
        """
        master, slave = pty.openpty()
        _set_window_size(master, *size)
        setsid = shutil.which("setsid")
        argv = [setsid, "--ctty", "--", *command] if setsid else list(command)
        try:
            self._process = subprocess.Popen(  # pylint: disable=consider-using-with
                argv,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env={**os.environ, **_ENVIRONMENT},
                # setsid makes its own session; either way the installer leads a
                # process group of its own, to stop all of it at once
                start_new_session=setsid is None,
            )
        except OSError:
            os.close(master)
            raise
        finally:
            os.close(slave)
        self._master = master
        wake_read, wake_write = os.pipe()
        threading.Thread(
            target=self._pump, args=(log_path, wake_read), name="installer-output", daemon=True
        ).start()
        threading.Thread(
            target=self._wait, args=(wake_write,), name="installer-wait", daemon=True
        ).start()

    def _wait(self, wake_fd: int) -> None:
        """Thread body: tell the reader when the installer is gone."""
        assert self._process is not None
        self._process.wait()
        os.write(wake_fd, b"x")
        os.close(wake_fd)

    def _pump(self, log_path: Path, wake_fd: int) -> None:
        """Thread body: pty -> log file + pending text, then the exit status.

        After the installer exits, what is left in the pty is still read, but
        a leftover child of it holding the pty open does not keep us waiting.
        """
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        log = None
        with contextlib.suppress(OSError):
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log = log_path.open("wb")  # pylint: disable=consider-using-with
        watched = [self._master, wake_fd]
        try:
            while True:
                ready, _, _ = select.select(watched, [], [], 0 if len(watched) == 1 else None)
                if self._master in ready:
                    try:
                        chunk = os.read(self._master, _READ_SIZE)
                    except OSError:  # EIO: nobody has the pty open any more
                        chunk = b""
                    if not chunk:
                        break
                    if log is not None:
                        log.write(chunk)
                    self._push(decoder.decode(chunk))
                elif wake_fd in ready:
                    watched = [self._master]  # exited: drain what is left
                else:
                    break
            self._push(decoder.decode(b"", final=True))
        finally:
            if log is not None:
                log.close()
            os.close(wake_fd)
            with self._lock:
                os.close(self._master)
                self._master = -1
            assert self._process is not None
            status = self._process.wait()
            with self._lock:
                self.returncode = status
            self._notify()

    def _push(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._pending.append(text)
            if self._woken:
                return
            self._woken = True
        self._notify()

    def take_output(self) -> str:
        """Everything printed since the last call."""
        with self._lock:
            text = "".join(self._pending)
            self._pending.clear()
            self._woken = False
        return text

    def write(self, data: bytes) -> None:
        """Send keyboard input to the installer (ignored once it is gone)."""
        with self._lock:
            if self._master >= 0 and data:
                with contextlib.suppress(OSError):
                    os.write(self._master, data)

    def resize(self, columns: int, rows: int) -> None:
        """Follow a change of size of the terminal box."""
        with self._lock:
            if self._master >= 0:
                _set_window_size(self._master, columns, rows)

    @property
    def finished(self) -> bool:
        """True once the process has exited and its output was read."""
        with self._lock:
            return self.returncode is not None

    def terminate(self) -> None:
        """Stop the installer and everything it started."""
        if self._process is None or self._process.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self._process.pid, signal.SIGTERM)
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self._process.pid, signal.SIGKILL)
