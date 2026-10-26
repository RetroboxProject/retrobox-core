from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

_logger = logging.getLogger(__name__)


def _runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))


def pipewire_is_available() -> bool:
    socket = _runtime_dir() / "pipewire-0"
    if not socket.exists():
        _logger.debug("Socket de PipeWire no encontrado en %s", socket)
        return False
    try:
        result = subprocess.run(
            ["pw-cli", "info", "0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        # sin pw-cli, nos fiamos del socket
        return True
    return result.returncode == 0


def pulse_is_available() -> bool:
    socket = _runtime_dir() / "pulse" / "native"
    if socket.exists():
        return True
    try:
        result = subprocess.run(
            ["pactl", "info"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def alsa_is_available() -> bool:
    return Path("/proc/asound/cards").exists()