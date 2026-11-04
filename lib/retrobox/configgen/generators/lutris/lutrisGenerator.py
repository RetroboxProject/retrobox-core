"""Generator for Lutris games.

A Lutris "rom" holds ``lutris:rungameid/<id>``. Most games are left to
Lutris, which waits for them. Games whose Wine prefix belongs to a
third-party launcher (Ubisoft Connect, EA) keep that launcher running after
the game exits, so they get a bash wrapper that waits for the game's .exe
and then purges the launcher and the prefix's wineserver.
"""

# the module name follows the <emulator>Generator convention of generators/importer.py
# pylint: disable=invalid-name

from __future__ import annotations

import glob
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

from retrobox.configgen.utils.pc_launchers import launcher_environment
from retrobox.paths import RUNTIME_DIR

from ... import Command
from ...exceptions import RetroboxException
from ..Generator import Generator


# Timing of the wrapper
POLL_INTERVAL = 3  # seconds between two checks
LAUNCH_TIMEOUT = 90  # longest wait for the game's .exe to show up
MAX_TOTAL = 7200  # global safety timeout (2 h)

EXIT_TIMEOUT = 10.0
"""Seconds a Lutris game (often Wine) has to quit after SIGTERM."""

# Processes purged on exit, by launcher
UBISOFT_PROCS = [
    "UbisoftConnect.exe",
    "UbisoftGameLauncher.exe",
    "upc.exe",
    "UplayWebCore.exe",
]

EA_PROCS = [
    "EADesktop.exe",
    "EABackgroundService.exe",
    "EALauncher.exe",
    "Origin.exe",
    "OriginWebHelperService.exe",
]

# Wrapper executables that are NEVER the game's process
WRAPPER_BASENAMES = [
    "steam.exe",
]

# Wine prefixes of third-party launchers in the Lutris YAML. A game whose
# prefix matches one of them gets the bash wrapper (case-insensitive regexes,
# to cover variations in case and paths).
THIRD_PARTY_PREFIX_PATTERNS: list[tuple[re.Pattern[str], list[str]]] = [
    (
        re.compile(r"ubisoft.connect|uplay", re.IGNORECASE),
        UBISOFT_PROCS,
    ),
    (
        re.compile(r"ea.?desktop|origin|ea.?games", re.IGNORECASE),
        EA_PROCS,
    ),
]

_LINK_PREFIX = "lutris:rungameid/"


# ─────────────────────────────────────────────────────────────────────────────
# Python helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_lutris_info(game_id: str) -> tuple[str, str]:
    """Run ``lutris -l`` and return (slug, name) for the numeric game id.

    Line format: ``ID | slug | Game name | ...``
    """
    try:
        output = subprocess.check_output(
            ["lutris", "-l"], text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        raise RetroboxException(f"Cannot run 'lutris -l': {err}") from err

    for line in output.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) >= 3 and parts[0] == game_id:
            return parts[2], parts[1]

    raise RetroboxException(f"No game with id {game_id} in 'lutris -l'")


def _parse_lutris_yml(slug: str) -> tuple[str, str]:
    """Find the newest YAML of the slug and return (exe basename, Wine prefix)."""
    conf_dir = Path.home() / ".local/share/lutris/games"
    candidates = sorted(
        conf_dir.glob(f"{slug}*.yml"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RetroboxException(f"No .yml file for slug '{slug}' in {conf_dir}")

    yml_path = candidates[0]
    exe_path = ""
    wine_prefix = ""

    with yml_path.open(encoding="utf-8") as yml:
        for line in yml:
            if line.startswith("  exe: ") and not exe_path:
                exe_path = line.removeprefix("  exe: ").strip()
            if line.startswith("  prefix: ") and not wine_prefix:
                wine_prefix = line.removeprefix("  prefix: ").strip()

    if not exe_path:
        raise RetroboxException(f"No 'exe:' in {yml_path}")

    return Path(exe_path).name, wine_prefix


def _read_link(rom: Path) -> str:
    """The ``lutris:rungameid/<id>`` link stored in the rom file."""
    try:
        link = Path(rom).read_text(encoding="utf-8").strip()
    except OSError as err:
        raise RetroboxException(f"Cannot read the Lutris link {rom}: {err}") from err
    if not link.startswith(_LINK_PREFIX):
        raise RetroboxException(f"Unknown Lutris link format: '{link}'")
    return link


def _resolve_game(link: str) -> tuple[str, str]:
    """id -> (slug, name) -> YAML -> (exe basename, Wine prefix)."""
    slug, _name = _get_lutris_info(link.removeprefix(_LINK_PREFIX))
    return _parse_lutris_yml(slug)


def _detect_third_party_launcher(wine_prefix: str) -> list[str] | None:
    """The processes to purge when the prefix belongs to a third-party launcher.

    None when the game uses no known launcher (manual Wine, native, etc.).
    """
    if not wine_prefix:
        return None

    for pattern, procs in THIRD_PARTY_PREFIX_PATTERNS:
        if pattern.search(wine_prefix):
            return procs

    return None


def _prefix_forms(wine_prefix: str) -> list[str]:
    """The ways WINEPREFIX may spell the prefix in a process environment."""
    if not wine_prefix:
        return []
    expanded = os.path.expanduser(wine_prefix).rstrip("/")
    return sorted({wine_prefix, expanded, f"{expanded}/"})


# ─────────────────────────────────────────────────────────────────────────────
# Bash wrapper (third-party launchers only)
# ─────────────────────────────────────────────────────────────────────────────

def _make_wrapper(
    lutris_link: str,
    exe_name: str,
    wine_prefix: str,
    procs_to_purge: list[str],
) -> str:
    """Write a temporary bash script and return its path. The script:

    1. starts the game through ``lutris <link>`` (fire and forget);
    2. waits up to LAUNCH_TIMEOUT for the game's .exe to show up;
    3. watches the .exe until it ends;
    4. purges the launcher's processes (Ubisoft Connect / EA) and wineserver.

    Only used for third-party launcher prefixes; other games run through
    lutris directly.
    """
    purge_lines = "\n".join(
        f'pkill -f "{proc}" 2>/dev/null || true' for proc in procs_to_purge
    )

    wineserver_kill = (
        f'WINEPREFIX="{wine_prefix}" wineserver -k 2>/dev/null || true'
        if wine_prefix
        else "# (no Wine prefix found)"
    )

    wrapper_excl = "|".join(re.escape(name) for name in WRAPPER_BASENAMES)

    script = f"""\
#!/usr/bin/env bash
set -uo pipefail
trap 'rm -f "$0"' EXIT

EXE_NAME="{exe_name}"
WRAPPER_EXCL_RE="({wrapper_excl})$"
LAUNCH_TIMEOUT={LAUNCH_TIMEOUT}
POLL={POLL_INTERVAL}
MAX_TOTAL={MAX_TOTAL}
START=$(date +%s)

_elapsed() {{ echo $(( $(date +%s) - START )); }}
_timeout()  {{ [ "$(_elapsed)" -ge "$MAX_TOTAL" ]; }}

_game_running() {{
    local proc cmd base
    for proc in /proc/[0-9]*/cmdline; do
        [ -r "$proc" ] || continue
        cmd=$( {{ tr '\\0' '\\n' < "$proc" 2>/dev/null || true; }} 2>/dev/null | head -n1)
        [ -z "$cmd" ] && continue
        base="${{cmd##*[\\\\/]}}"
        if [[ "$base" =~ $WRAPPER_EXCL_RE ]]; then
            continue
        fi
        if [[ "$cmd" =~ ^[A-Za-z]:.*"$EXE_NAME"$ ]]; then
            return 0
        fi
    done
    return 1
}}

# 1. Start the game through Lutris (fire and forget)
echo "[lutris-wrapper] Running: lutris {lutris_link}"
lutris "{lutris_link}" > /dev/null 2>&1 &

# 2. Wait for the game's .exe
echo "[lutris-wrapper] Waiting for '$EXE_NAME' to start..."
APPEARED=0
DEADLINE=$(( START + LAUNCH_TIMEOUT ))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    if _game_running; then
        APPEARED=1
        break
    fi
    sleep "$POLL"
done

if [ "$APPEARED" -eq 0 ]; then
    echo "[lutris-wrapper] Timeout: '$EXE_NAME' not seen after ${{LAUNCH_TIMEOUT}}s."
    exit 1
fi

echo "[lutris-wrapper] '$EXE_NAME' is running. Watching it..."

# 3. Watch until the game closes
while true; do
    _timeout && echo "[lutris-wrapper] Global timeout reached, leaving." && exit 0

    if ! _game_running; then
        sleep 5
        if ! _game_running; then
            echo "[lutris-wrapper] '$EXE_NAME' has ended."
            break
        fi
        echo "[lutris-wrapper] False alarm, '$EXE_NAME' is still running."
    fi

    sleep "$POLL"
done

# 4. Purge the third-party launcher
echo "[lutris-wrapper] Purging the launcher's processes..."
{purge_lines}

echo "[lutris-wrapper] Killing the prefix's wineserver..."
{wineserver_kill}

echo "[lutris-wrapper] Cleanup done."
exit 0
"""

    fd, path = tempfile.mkstemp(prefix="lutris_wrapper_", suffix=".sh", dir=RUNTIME_DIR)
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path


def _remove_old_wrappers() -> None:
    """Delete the wrappers left behind by earlier launches."""
    for old in glob.glob(str(RUNTIME_DIR / "lutris_wrapper_*.sh")):
        try:
            os.remove(old)
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Generator
# ─────────────────────────────────────────────────────────────────────────────

class LutrisGenerator(Generator):
    """Runs a Lutris game, through the wrapper when a third-party launcher is involved."""

    def __init__(self) -> None:
        self._wine_prefix = ""

    # the signature is fixed by the Generator interface
    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        """Return ``lutris <link>``, or the wrapper for third-party launchers."""
        _remove_old_wrappers()
        lutris_link = _read_link(rom)
        exe_name, wine_prefix = _resolve_game(lutris_link)
        self._wine_prefix = wine_prefix
        environment = launcher_environment(system, playersControllers)

        procs_to_purge = _detect_third_party_launcher(wine_prefix)
        if procs_to_purge is not None:
            # a third-party launcher (Ubisoft Connect, EA) outlives the game:
            # the wrapper notices the end of the game and purges it
            wrapper_path = _make_wrapper(lutris_link, exe_name, wine_prefix, procs_to_purge)
            return Command.Command(array=[wrapper_path], env=environment)

        # native game, plain Wine, manual install...: Lutris waits for the game
        return Command.Command(array=["lutris", lutris_link], env=environment)

    def exit_env(self, system, rom):
        """Every process of a Wine game (wineserver included) carries its WINEPREFIX."""
        forms = _prefix_forms(self._wine_prefix)
        return {"WINEPREFIX": forms} if forms else {}

    def exit_timeout(self, config):
        """Wine games take a while to close."""
        return EXIT_TIMEOUT
