"""Compare the BIOS declared in share/systems with batocera's list.

batocera keeps the BIOS of its systems in ``batocera-systems`` (a Python
script of batocera.linux). Retrobox declares its own, in the ``bios:`` block
of each system's YAML (see lib/retrobox/bios.py), which is the reference;
this tool only says where batocera knows more::

    python3 dev/batocera_bios.py               # files and MD5s batocera has and we lack
    python3 dev/batocera_bios.py --draft fds   # a draft bios: block for one system
    python3 dev/batocera_bios.py --source FILE # a local copy instead of downloading it

A file batocera lists is reported when no declaration of the same system
names it, and a MD5 when the declaration of that file lacks it. Some of what
batocera lists is for emulators Retrobox doesn't have (XRoar, the openMSX
machines...) or outside the BIOS folder: _NOT_OURS leaves those out. A draft
makes every file optional: which ones an emulator can't run without, and
which are alternatives of one another (one_of), is decided by hand.

Run it from the repository root (it reads the systems with retrobox.bios).
It exits with 1 when there are differences and 2 when batocera's list can't
be read, so CI (.github/workflows/upstream.yml) tells one from the other.
"""

from __future__ import annotations

import argparse
import ast
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

# pylint: disable-next=wrong-import-position  # needs the path above
from retrobox.bios import BiosError, parse

SOURCE_URL = (
    "https://raw.githubusercontent.com/batocera-linux/batocera.linux/master/"
    "package/batocera/core/batocera-scripts/scripts/batocera-systems"
)
# path prefixes of batocera's list that are not for Retrobox's emulators
_NOT_OURS = ("xroar/", "openmsx/", "../saves/", "saves/")
# where Retrobox's emulators read what batocera keeps elsewhere
_OUR_PATHS = {"ps2/": "pcsx2/bios/"}


def read_batocera(source: str | None) -> dict[str, Any]:
    """The ``systems`` dictionary of batocera-systems (read, never run)."""
    if source:
        text = Path(source).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
            text = response.read().decode("utf-8")
    start = text.index("{", text.index("systems = {"))
    depth = 0
    for index in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            return ast.literal_eval(text[start:index + 1])
    raise ValueError("no systems dictionary in batocera-systems")


def batocera_files(entry: dict[str, Any]) -> dict[str, set[str]]:
    """The files of one batocera system, relative to the BIOS folder, with their MD5s.

    A zip counts as one file, without MD5: the MD5 of a set changes from one
    MAME version (or one repack) to another while its content still works.
    """
    files: dict[str, set[str]] = defaultdict(set)
    for bios_file in entry["biosFiles"]:
        path = bios_file["file"].removeprefix("bios/")
        if path.startswith(_NOT_OURS):
            continue
        for theirs, ours in _OUR_PATHS.items():
            if path.startswith(theirs):
                path = ours + path.removeprefix(theirs)
        md5 = bios_file.get("md5") or ""
        files[path].update(
            set() if path.endswith(".zip") or not md5
            else set(md5 if isinstance(md5, list) else [md5])
        )
    return dict(files)


def our_systems() -> dict[str, Path]:
    """Every system YAML of share/systems, by system name."""
    return {path.stem: path for path in (REPO_ROOT / "share" / "systems").rglob("*.yaml")}


def declared(path: Path, system: str) -> dict[str, set[str]]:
    """The files the bios: block of a system declares, with their MD5s."""
    # pylint: disable-next=import-outside-toplevel
    import yaml

    content = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(system) or {}
    files: dict[str, set[str]] = defaultdict(set)
    for requirement in parse(system, content):
        for bios_file in requirement.files:
            files[bios_file.path].update(bios_file.md5)
    return dict(files)


def report(batocera: dict[str, Any]) -> int:
    """Print what batocera has and our declarations lack; 1 if anything."""
    ours = our_systems()
    differences = 0
    for system in sorted(batocera):
        if system not in ours:
            continue
        try:
            have = declared(ours[system], system)
        except BiosError as error:
            print(f"{system}: invalid bios block: {error}")
            differences += 1
            continue
        for path, md5s in sorted(batocera_files(batocera[system]).items()):
            if path not in have:
                print(f"{system}: {path} is not declared")
                differences += 1
            elif md5s - have[path]:
                print(f"{system}: {path} lacks md5 {', '.join(sorted(md5s - have[path]))}")
                differences += 1
    print(f"{differences} difference(s) with batocera's list")
    return 1 if differences else 0


def draft(batocera: dict[str, Any], system: str) -> str:
    """A bios: block for ``system`` with every batocera file, all optional."""
    lines = ["  bios:"]
    for path, md5s in sorted(batocera_files(batocera[system]).items()):
        lines.append(f"  - file: {path}")
        if len(md5s) == 1:
            lines.append(f"    md5: {next(iter(md5s))}")
        elif md5s:
            lines.append(f"    md5: [{', '.join(sorted(md5s))}]")
        lines.append("    optional: true")
    return "\n".join(lines)


def main() -> int:
    """Compare with batocera's list, or print a draft."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--source", help="a local copy of batocera-systems")
    parser.add_argument("--draft", metavar="SYSTEM", help="print a draft bios: block")
    args = parser.parse_args()
    try:
        batocera = read_batocera(args.source)
    except (OSError, ValueError, SyntaxError) as error:  # urllib's errors are OSErrors
        print(f"cannot read batocera's list: {error}", file=sys.stderr)
        return 2
    if args.draft:
        if args.draft not in batocera:
            print(f"batocera has no BIOS for {args.draft}", file=sys.stderr)
            return 1
        print(draft(batocera, args.draft))
        return 0
    return report(batocera)


if __name__ == "__main__":
    sys.exit(main())
