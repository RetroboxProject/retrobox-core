"""
Legacy .env loader and retrobox.ini generator.

NOTE: this predates the self-bootstrapping retrobox.ini logic now in
retrobox.paths._base (_ensure_retrobox_ini / _bootstrap_env). That module
already creates and repairs retrobox.ini on its own using the
[paths] / [environ] section split, so generate_retrobox_ini() below is
stale: it still writes everything into a single [retrobox] section,
which _base.py no longer reads. Keep this in mind before wiring this
module back into anything.
"""

from __future__ import annotations

import os
from pathlib import Path

from retrobox.paths._base import CaseSensitiveConfigParser
from retrobox.paths import RETROBOX_INI


def load_env(env_path: Path) -> dict[str, str]:
    """
    Parse a simple KEY=VALUE .env file into a dict.

    Blank lines, comments ("#") and lines without "=" are skipped.
    Values are stripped of surrounding whitespace and matching quotes.
    An empty value (e.g. "VAR=" or 'VAR=""') is treated as "unset": it
    is left out of the result so callers fall back to their own
    default instead of having it overwritten with "".

    Args:
        env_path: Path to the .env file to read.

    Returns:
        A dict of the key/value pairs found. Empty if the file does
        not exist.
    """
    env: dict[str, str] = {}
    if not env_path.is_file():
        return env

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            env[key] = value

    return env


def apply_env_defaults(rootdir: Path | str) -> None:
    """
    Load `<rootdir>/.env` and apply its keys as environment defaults.

    Uses os.environ.setdefault(), so any value already present in the
    process environment takes precedence over the .env file.

    Args:
        rootdir: Root directory containing the .env file.
    """
    env_path = Path(rootdir) / ".env"
    for key, value in load_env(env_path).items():
        os.environ.setdefault(key, value)


def generate_retrobox_ini(rootdir: Path | str) -> Path:
    """
    Generate retrobox.ini from the keys defined in .env.

    Must be called AFTER retrobox.paths has been imported, so that
    RETROBOX_INI can be resolved.

    Args:
        rootdir: Root directory containing the .env file.

    Returns:
        Path to the generated retrobox.ini file.
    """

    env_path = Path(rootdir) / ".env"
    env_vars = load_env(env_path)

    config = CaseSensitiveConfigParser()
    config["retrobox"] = env_vars

    RETROBOX_INI.parent.mkdir(parents=True, exist_ok=True)
    with RETROBOX_INI.open("w", encoding="utf-8") as f:
        config.write(f)

    return RETROBOX_INI