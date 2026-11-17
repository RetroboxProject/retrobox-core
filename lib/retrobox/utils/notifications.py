"""
Desktop notification helpers.

Uses `notify-send` (Freedesktop.org standard) with fallbacks to `zenity`
(modal dialog, works everywhere) and `kdialog` (KDE native). Handles
D-Bus environment variables to ensure it works even if the script is
launched from a non-standard shell context.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Notification:
    """What to show, and how."""

    summary: str
    body: str
    urgency: str
    icon: str
    app_name: str
    timeout_ms: int

    @property
    def critical(self) -> bool:
        """Whether it reports an error."""
        return self.urgency == "critical"


def _get_dbus_address() -> str | None:
    """
    Ensure we have a valid D-Bus session address.
    Falls back to the default user socket path if the env var is missing.
    """
    if "DBUS_SESSION_BUS_ADDRESS" in os.environ:
        return os.environ["DBUS_SESSION_BUS_ADDRESS"]

    # Fallback for standard systemd user sessions
    default_bus_path = f"/run/user/{os.getuid()}/bus"
    if os.path.exists(default_bus_path):
        return f"unix:path={default_bus_path}"

    return None


def _run(
    command: list[str], env: dict[str, str], timeout: float, ok_codes: tuple[int, ...] = (0,)
) -> bool:
    """Run one notifier; whether it worked (its exit code is in ``ok_codes``)."""
    name = os.path.basename(command[0])
    try:
        result = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as err:
        _logger.debug("%s execution error: %s", name, err)
        return False
    if result.returncode in ok_codes:
        return True
    _logger.debug("%s failed: %s", name, result.stderr.strip())
    return False


def _notify_send(binary: str, note: _Notification, env: dict[str, str]) -> bool:
    """A non-blocking toast, the standard way."""
    command = [
        binary,
        "--app-name", note.app_name,
        "--urgency", note.urgency,
        "--icon", note.icon,
        "--expire-time", str(note.timeout_ms),
        note.summary,
    ]
    if note.body:
        command.append(note.body)
    return _run(command, env, timeout=2)


def _zenity(binary: str, note: _Notification, env: dict[str, str]) -> bool:
    """A modal dialog: blocks until it is closed."""
    kind = "--error" if note.critical else "--info"
    command = [
        binary, "--title", note.app_name, "--width", "400",
        kind, "--text", f"<b>{note.summary}</b>\n\n{note.body}",
    ]
    # zenity returns 0 on OK, 1 on cancel/close, 5 on timeout
    return _run(command, env, timeout=30, ok_codes=(0, 1))


def _kdialog(binary: str, note: _Notification, env: dict[str, str]) -> bool:
    """KDE's dialog (may be non-modal in Plasma 6)."""
    command = [binary, "--title", note.app_name]
    if note.critical:
        # --sorry instead of --error for better Plasma 6 compatibility
        command += ["--sorry", f"{note.summary}\n\n{note.body}"]
    else:
        # --passivepopup with a longer timeout (30 seconds)
        command += ["--passivepopup", f"{note.summary}\n{note.body}", "30"]
    return _run(command, env, timeout=5)


_NOTIFIERS = (("notify-send", _notify_send), ("zenity", _zenity), ("kdialog", _kdialog))


def send_desktop_notification(  # pylint: disable=too-many-arguments
    summary: str,
    body: str = "",
    *,
    urgency: str = "normal",
    icon: str = "dialog-information",
    app_name: str = "Retrobox",
    timeout_ms: int = 10000,
) -> bool:
    """
    Send a desktop notification via `notify-send`, `zenity`, or `kdialog`.

    Priority order:
    1. notify-send (standard, non-blocking toast)
    2. zenity (modal dialog, blocks until closed)
    3. kdialog (KDE native, may be non-modal in Plasma 6)
    """
    env = os.environ.copy()
    dbus_addr = _get_dbus_address()
    if dbus_addr:
        env["DBUS_SESSION_BUS_ADDRESS"] = dbus_addr

    note = _Notification(summary, body, urgency, icon, app_name, timeout_ms)
    for name, notifier in _NOTIFIERS:
        binary = shutil.which(name)
        if binary and notifier(binary, note, env):
            return True
    return False


def notify_error(summary: str, body: str = "") -> bool:
    """Convenience wrapper for error-level notifications."""
    return send_desktop_notification(
        summary,
        body,
        urgency="critical",
        icon="dialog-error",
        timeout_ms=15000,  # 15 seconds for errors
    )
