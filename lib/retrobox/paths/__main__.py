"""Print the directories Retrobox resolved, for non-Python callers.

    python3 -m retrobox.paths            human-readable NAME=value lines
    python3 -m retrobox.paths --shell    `export NAME='value'` lines, ready
                                        for `eval "$(...)"` in bash
    python3 -m retrobox.paths --get SECTION.KEY [DEFAULT]
                                        one value of the merged retrobox.ini
                                        (/etc/retrobox + ~/.config/retrobox)

Run it from the project root (or with it on PYTHONPATH). Importing the
package creates the config/data/state directories on first use, exactly as
the launcher would. retrobox.ini itself is never written.
"""

from __future__ import annotations

import shlex
import sys

from ._base import get_ini_value
from ._env import exported_environment


def main(argv: list[str]) -> int:
    """Entry point; returns the process exit code."""
    if argv and argv[0] == "--get":
        if not 2 <= len(argv) <= 3 or "." not in argv[1]:
            print(__doc__, file=sys.stderr)
            return 2
        section, key = argv[1].split(".", 1)
        print(get_ini_value(section, key, argv[2] if len(argv) == 3 else ""))
        return 0
    if any(arg not in ("--shell",) for arg in argv):
        print(__doc__, file=sys.stderr)
        return 2
    shell = "--shell" in argv
    for name, value in exported_environment().items():
        print(f"export {name}={shlex.quote(str(value))}" if shell else f"{name}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
