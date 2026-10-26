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

_logger = logging.getLogger(__name__)


def _get_dbus_address() -> str | None:
    """
    Ensure we have a valid D-Bus session address.
    Falls back to the default user socket path if the env var is missing.
    """
    if "DBUS_SESSION_BUS_ADDRESS" in os.environ:
        return os.environ["DBUS_SESSION_BUS_ADDRESS"]
    
    # Fallback for standard systemd user sessions
    uid = os.getuid()
    default_bus_path = f"/run/user/{uid}/bus"
    if os.path.exists(default_bus_path):
        return f"unix:path={default_bus_path}"
    
    return None


def send_desktop_notification(
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

    # 1. Try notify-send first (Universal, non-blocking)
    notify_send = shutil.which("notify-send")
    if notify_send:
        cmd = [
            notify_send,
            "--app-name", app_name,
            "--urgency", urgency,
            "--icon", icon,
            "--expire-time", str(timeout_ms),
            summary,
        ]
        if body:
            cmd.append(body)

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return True
            else:
                _logger.debug("notify-send failed: %s", result.stderr.strip())
        except (subprocess.SubprocessError, OSError) as e:
            _logger.debug("notify-send execution error: %s", e)

    # 2. Fallback to zenity (modal, blocks until user closes it)
    zenity = shutil.which("zenity")
    if zenity:
        zt_cmd = [zenity, "--title", app_name, "--width", "400"]
        if urgency == "critical":
            zt_cmd.extend(["--error", "--text", f"<b>{summary}</b>\n\n{body}"])
        else:
            zt_cmd.extend(["--info", "--text", f"<b>{summary}</b>\n\n{body}"])
        
        try:
            result = subprocess.run(
                zt_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,  # zenity blocks, so give it time
            )
            # zenity returns 0 on OK, 1 on cancel/close, 5 on timeout
            if result.returncode in (0, 1):
                return True
            else:
                _logger.debug("zenity failed: %s", result.stderr.strip())
        except (subprocess.SubprocessError, OSError) as e:
            _logger.debug("zenity execution error: %s", e)

    # 3. Last resort: kdialog (KDE native, may be non-modal in Plasma 6)
    kdialog = shutil.which("kdialog")
    if kdialog:
        kd_cmd = [kdialog, "--title", app_name]
        if urgency == "critical":
            # Use --sorry instead of --error for better Plasma 6 compatibility
            kd_cmd.extend(["--sorry", f"{summary}\n\n{body}"])
        else:
            # --passivepopup with a longer timeout (30 seconds)
            kd_cmd.extend(["--passivepopup", f"{summary}\n{body}", "30"])
        
        try:
            result = subprocess.run(
                kd_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
            else:
                _logger.debug("kdialog failed: %s", result.stderr.strip())
        except (subprocess.SubprocessError, OSError) as e:
            _logger.debug("kdialog execution error: %s", e)

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