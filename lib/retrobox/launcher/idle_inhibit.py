"""Keep the computer awake while a game runs.

A game is often played with a controller only, and most desktops do not count
controller input as activity: the screen would dim, turn off or lock, or the
computer would go to sleep, in the middle of a game. While a game runs (its
hooks included) Retrobox holds two inhibitors, and releases them when the game
is over. Outside games (in EmulationStation) nothing is held, so the desktop's
own power settings apply there.

* **logind** (``systemd-inhibit``, or ``elogind-inhibit``): a ``block``
  inhibitor of ``idle`` and ``sleep``. It stops automatic suspend, and the
  desktops that follow logind's idle inhibitors (KDE Plasma among them) keep
  the screen on as well. Closing a laptop's lid still suspends it
  (``LidSwitchIgnoreInhibited``).
* **org.freedesktop.ScreenSaver** on the session bus, through ``jeepney`` when
  it is installed: what KDE Plasma, Xfce and most others use to keep the
  screen on and unlocked. The desktop drops it by itself if the connection
  that took it closes, so a launcher that dies cannot leave the screen on.

The ``systemd-inhibit`` helper runs ``tail --pid=<launcher>``, so it also
ends by itself when the launcher dies. Neither inhibitor is required: when
one cannot be taken the game starts anyway, and the log says why.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

    from jeepney import DBusAddress
    from jeepney.io.blocking import DBusConnection

_logger = logging.getLogger(__name__)

_WHO: Final = "Retrobox"
_INHIBIT_BINARIES: Final = ("systemd-inhibit", "elogind-inhibit")
_WHAT: Final = "idle:sleep"
# systemd-inhibit exits at once when logind refuses the lock (no logind, or
# polkit says no): give it this long to fail before trusting it.
_START_CHECK_SECONDS: Final = 0.3
_STOP_TIMEOUT_SECONDS: Final = 2.0
_DBUS_TIMEOUT_SECONDS: Final = 2.0

_SCREENSAVER_PATH: Final = "/org/freedesktop/ScreenSaver"
_SCREENSAVER_NAME: Final = "org.freedesktop.ScreenSaver"


def _start_logind_inhibitor(reason: str) -> subprocess.Popen[bytes] | None:
    """Take logind's idle and sleep lock; return the process that holds it.

    The lock lasts as long as the returned process, which waits for this
    process (the launcher) to exit, in case it is never stopped.
    """
    binary = next((found for name in _INHIBIT_BINARIES if (found := shutil.which(name))), None)
    tail = shutil.which("tail")
    if binary is None or tail is None:
        _logger.debug("No systemd-inhibit or elogind-inhibit: not blocking sleep through logind")
        return None

    command = [
        binary,
        f"--what={_WHAT}",
        f"--who={_WHO}",
        f"--why={reason}",
        "--mode=block",
        tail,
        f"--pid={os.getpid()}",
        "-f",
        "/dev/null",
    ]
    try:
        # its own session: the signals sent to the launcher's process group
        # (Ctrl+C on a terminal) do not drop the lock before the launcher does
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as err:
        _logger.warning("Cannot run %s: %s", binary, err)
        return None

    try:
        status = process.wait(timeout=_START_CHECK_SECONDS)
    except subprocess.TimeoutExpired:
        _logger.debug("Holding logind's %s inhibitor (%s)", _WHAT, binary)
        return process

    error = process.stderr.read().decode(errors="replace").strip() if process.stderr else ""
    _logger.warning(
        "Could not block sleep through logind (%s exited with %d)%s",
        os.path.basename(binary),
        status,
        f": {error}" if error else "",
    )
    return None


def _stop_logind_inhibitor(process: subprocess.Popen[bytes]) -> None:
    """End the process that holds logind's lock, which releases it."""
    process.terminate()
    try:
        process.wait(timeout=_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    if process.stderr:
        process.stderr.close()


class _ScreenSaverInhibitor:
    """org.freedesktop.ScreenSaver's inhibitor, held over a session bus connection.

    Needs ``jeepney`` and a session bus; without either nothing is held.
    """

    def __init__(self) -> None:
        self._connection: DBusConnection | None = None
        self._address: DBusAddress | None = None
        self._cookie: int | None = None

    def take(self, reason: str) -> None:
        """Ask the screen saver service not to blank or lock the screen."""
        try:
            # pylint: disable=import-outside-toplevel
            from jeepney import DBusAddress as Address, new_method_call
            from jeepney.io.blocking import open_dbus_connection
            from jeepney.wrappers import DBusErrorResponse, unwrap_msg
        except ImportError:
            _logger.debug("jeepney is not installed: not inhibiting the screen saver over D-Bus")
            return

        try:
            connection = open_dbus_connection(bus="SESSION")
        except (OSError, KeyError, ValueError) as err:
            # KeyError: no DBUS_SESSION_BUS_ADDRESS; ValueError: an address jeepney can't use
            _logger.debug("No session bus (%s): not inhibiting the screen saver over D-Bus", err)
            return

        address = Address(
            _SCREENSAVER_PATH, bus_name=_SCREENSAVER_NAME, interface=_SCREENSAVER_NAME
        )
        try:
            reply = connection.send_and_get_reply(
                new_method_call(address, "Inhibit", "ss", (_WHO, reason)),
                timeout=_DBUS_TIMEOUT_SECONDS,
            )
            cookie = unwrap_msg(reply)[0]
        except (DBusErrorResponse, OSError, TimeoutError) as err:
            # most often: no screen saver service on this desktop
            _logger.debug("%s.Inhibit failed: %s", _SCREENSAVER_NAME, err)
            connection.close()
            return

        self._connection, self._address, self._cookie = connection, address, cookie
        _logger.debug("Holding the screen saver inhibitor (cookie %s)", cookie)

    def release(self) -> None:
        """Give the inhibitor back and close the connection (which releases it too)."""
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            # pylint: disable=import-outside-toplevel
            from jeepney import new_method_call

            connection.send_and_get_reply(
                new_method_call(self._address, "UnInhibit", "u", (self._cookie,)),
                timeout=_DBUS_TIMEOUT_SECONDS,
            )
        except (OSError, TimeoutError) as err:
            _logger.debug("%s.UnInhibit failed: %s", _SCREENSAVER_NAME, err)
        finally:
            connection.close()
            _logger.debug("Released the screen saver inhibitor")


@contextlib.contextmanager
def inhibit_idle(reason: str) -> Iterator[None]:
    """Keep the screen on and the computer awake while the block runs.

    Args:
        reason: Why, as the desktop shows it (e.g. "Playing Super Metroid").
    """
    logind = _start_logind_inhibitor(reason)
    screensaver = _ScreenSaverInhibitor()
    try:
        screensaver.take(reason)
        yield
    finally:
        screensaver.release()
        if logind is not None:
            _stop_logind_inhibitor(logind)
            _logger.debug("Released logind's %s inhibitor", _WHAT)
