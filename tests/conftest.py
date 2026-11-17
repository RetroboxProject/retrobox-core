"""Shared setup of the test suite.

``retrobox.paths`` resolves every directory when it is imported, from the
environment and retrobox.ini. Before anything of Retrobox is imported, the
environment is pointed at a sandbox in a temporary directory, so the tests
never read or write the real home, /etc/retrobox or $XDG_RUNTIME_DIR.

Tests that need other directories or another retrobox.ini run Retrobox in a
subprocess with ``run_retrobox_module`` (the in-process modules keep what they
resolved at import time).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = REPO_ROOT / "lib"
SHARE_DIR = REPO_ROOT / "share"

_RETROBOX_VARIABLES = (
    "RETROBOX_CONFIGDIR",
    "RETROBOX_DATADIR",
    "RETROBOX_STATEDIR",
    "RETROBOX_RUNTIME_DIR",
    "RETROBOX_SYSCONFDIR",
    "RETROBOX_ROOTDIR",
    "RETROBOX_DEBUG",
    "BEZELS_DIR",
    "SHADERS_DIR",
    "SCREENSHOTS_DIR",
)


def sandbox_environment(root: Path) -> dict[str, str]:
    """An environment whose home, XDG and Retrobox directories are all under ``root``."""
    environment = {
        key: value for key, value in os.environ.items() if key not in _RETROBOX_VARIABLES
    }
    home = root / "home"
    directories = {
        "HOME": home,
        "XDG_CONFIG_HOME": home / ".config",
        "XDG_DATA_HOME": home / ".local" / "share",
        "XDG_STATE_HOME": home / ".local" / "state",
        "XDG_CACHE_HOME": home / ".cache",
        "XDG_RUNTIME_DIR": root / "run",
        "RETROBOX_SYSCONFDIR": root / "etc" / "retrobox",
    }
    for name, path in directories.items():
        path.mkdir(parents=True, exist_ok=True)
        environment[name] = str(path)
    os.chmod(directories["XDG_RUNTIME_DIR"], 0o700)
    environment["RETROBOX_ROOTDIR"] = str(REPO_ROOT)
    environment["PYTHONPATH"] = str(LIB_DIR)
    environment["NO_COLOR"] = "1"
    return environment


# --- the sandbox of this test session (set before any retrobox import) --------
_SESSION_ROOT = Path(tempfile.mkdtemp(prefix="retrobox-tests-"))
_SESSION_ENVIRONMENT = sandbox_environment(_SESSION_ROOT)
os.environ.clear()
os.environ.update(_SESSION_ENVIRONMENT)
sys.path.insert(0, str(LIB_DIR))


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Remove the session sandbox."""
    del session, exitstatus
    shutil.rmtree(_SESSION_ROOT, ignore_errors=True)


@pytest.fixture(name="session_root")
def fixture_session_root() -> Path:
    """The sandbox the in-process modules of Retrobox resolved their directories in."""
    return _SESSION_ROOT


def run_retrobox_module(
    root: Path,
    module: str,
    *args: str,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run ``python3 -m <module>`` in a fresh sandbox under ``root``.

    Args:
        root: Directory for the sandbox (a pytest ``tmp_path``).
        module: The module to run, e.g. ``retrobox.paths``.
        *args: Its arguments.
        env: Extra environment variables.
        check: Raise if the module exits with an error.

    Returns:
        The finished process, with its text output.
    """
    environment = sandbox_environment(root)
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=check,
        timeout=60,
    )


def run_python(
    root: Path, code: str, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a snippet of Python in a fresh sandbox under ``root`` (see run_retrobox_module)."""
    environment = sandbox_environment(root)
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )


def parse_assignments(output: str) -> dict[str, str]:
    """``NAME=value`` lines (the output of ``python3 -m retrobox.paths``) as a dict."""
    values = {}
    for line in output.splitlines():
        name, separator, value = line.partition("=")
        if separator:
            values[name] = value
    return values
