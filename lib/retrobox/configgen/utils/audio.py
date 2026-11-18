from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

_logger = logging.getLogger(__name__)


def _runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))


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
