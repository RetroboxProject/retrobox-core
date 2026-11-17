"""Hold configgen to its pylint baseline, so it only ever gets cleaner.

``lib/retrobox/configgen`` comes from batocera and does not pass pylint yet.
Instead of fixing it all at once, ``dev/pylint-baseline.json`` records how many
messages of each kind every file has today. The check fails when a file gets
a message it did not have before (a new file must be clean); fixing messages
only prints a reminder to lower the baseline::

    python3 dev/pylint_baseline.py            # check (what CI runs)
    python3 dev/pylint_baseline.py --update   # record the current state

Run it from the repository root, with the pylint of dev/requirements-dev.txt:
another pylint version reports other messages.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = "lib/retrobox/configgen"
BASELINE = REPO_ROOT / "dev" / "pylint-baseline.json"


def current_messages() -> dict[str, dict[str, int]]:
    """Run pylint on the target: {file: {message symbol: count}}."""
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "lib")}
    # duplicate-code is left out: pylint reports a duplicated block in only
    # one of the files that share it, and which one depends on the order the
    # files are found in, so the count moves between files from one machine
    # to the next. The code outside configgen is still checked for it.
    result = subprocess.run(
        [
            sys.executable, "-m", "pylint", "--output-format=json", "--score=n",
            "--disable=duplicate-code", TARGET,
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    # pylint's exit code is a bit mask of the message kinds; 32 is a usage error
    if result.returncode & 32 or not result.stdout.strip():
        sys.stderr.write(result.stderr)
        raise SystemExit("pylint did not run")
    counts: dict[str, Counter[str]] = {}
    for message in json.loads(result.stdout):
        counts.setdefault(message["path"], Counter())[message["symbol"]] += 1
    return {path: dict(sorted(symbols.items())) for path, symbols in sorted(counts.items())}


def compare(
    baseline: dict[str, dict[str, int]], current: dict[str, dict[str, int]]
) -> tuple[list[str], list[str]]:
    """The regressions and the improvements of ``current`` over ``baseline``."""
    worse: list[str] = []
    better: list[str] = []
    for path in sorted(set(baseline) | set(current)):
        before = baseline.get(path, {})
        after = current.get(path, {})
        for symbol in sorted(set(before) | set(after)):
            old, new = before.get(symbol, 0), after.get(symbol, 0)
            if new > old:
                worse.append(f"{path}: {symbol} {old} -> {new}")
            elif new < old:
                better.append(f"{path}: {symbol} {old} -> {new}")
    return worse, better


def main(argv: list[str] | None = None) -> int:
    """Check against the baseline, or record it with --update."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--update", action="store_true", help="record the current state")
    args = parser.parse_args(argv)

    current = current_messages()
    total = sum(sum(symbols.values()) for symbols in current.values())
    if args.update:
        BASELINE.write_text(json.dumps(current, indent=1) + "\n", encoding="utf-8")
        print(f"Baseline recorded: {total} messages in {len(current)} files")
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    worse, better = compare(baseline, current)
    for line in better:
        print(f"fixed:  {line}")
    if better:
        print("Lower the baseline with: python3 dev/pylint_baseline.py --update")
    for line in worse:
        print(f"NEW:    {line}")
    if worse:
        print(f"{len(worse)} new pylint message kind(s) in {TARGET}: fix them (see above).")
        print(f"Details: PYTHONPATH=lib python3 -m pylint {TARGET}/<file>")
        return 1
    print(f"configgen: {total} messages, none new over the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
