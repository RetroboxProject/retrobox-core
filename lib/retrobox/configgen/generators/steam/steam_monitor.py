"""Launch a Steam game and block until it has really finished.

Run as ``python3 -m retrobox.configgen.generators.steam.steam_monitor``. The
launcher waits for this process, so EmulationStation stays out of the way
for exactly as long as the game is alive.

Steam hands a launch over to its client and returns at once, so the game has
to be watched from outside. Before the game process exists Steam may spend a
long time preparing it (Vulkan shader pre-caching, an update, cloud sync, the
first run of a Proton prefix or of the Steam Linux Runtime), and some games
exit and are started again by Steam or by their own launcher. A fixed
timeout gets both cases wrong, so several signals are combined instead:

* the ``reaper SteamLaunch AppId=<id>`` process, which Steam keeps alive
  for as long as any process of the game runs (the main liveness signal);
* ``RunningAppID`` in Steam's ``registry.vdf`` (a fallback);
* ``GameAction`` lines for the AppId in Steam's console log, which say a
  launch is still being prepared;
* ``fossilize_replay`` working on the game's shader cache before launch.

The monitor goes through three states: waiting for the launch (patiently
while Steam reports progress), running, and lingering for a short grace
period after the game disappears, in case it comes back.
"""

from __future__ import annotations

import argparse
import enum
import logging
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import FrameType

_logger = logging.getLogger("steam-monitor")

POLL_INTERVAL = 2.0
"""Seconds between two checks."""

LINGER_POLL_INTERVAL = 0.5
"""Seconds between two checks once the game is gone, to return quickly."""

DEFAULT_STEAM_START_TIMEOUT = 300
"""Seconds to wait for the Steam client itself to appear."""

DEFAULT_LAUNCH_QUIET_TIMEOUT = 180
"""Seconds without any launch activity before giving up on the launch."""

DEFAULT_LAUNCH_MAX_TIMEOUT = 3600
"""Hard cap on the whole launch phase, however busy Steam claims to be."""

DEFAULT_EXIT_GRACE = 3
"""Seconds a game that ran for a while must stay gone to be finished.

Steam logs a new launch action within a second or two when it relaunches a
game, and its reaper outlives launcher-to-game handoffs, so a short wait is
enough once the game has really been played.
"""

DEFAULT_RELAUNCH_GRACE = 15
"""Seconds a game that only lived briefly must stay gone to be finished.

A short-lived first run is the typical shape of a game restarting itself
(after compiling shaders, applying settings, a launcher, ...).
"""

SHORT_RUN = 60
"""A run shorter than this many seconds gets DEFAULT_RELAUNCH_GRACE."""

DEFAULT_MAX_TOTAL = 24 * 3600
"""Safety cap on the whole session."""

_HOME = Path.home()
_STEAM_ROOTS = (
    _HOME / ".steam" / "steam",
    _HOME / ".local" / "share" / "Steam",
    _HOME / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
)
_REGISTRY_FILES = (
    _HOME / ".steam" / "registry.vdf",
    _HOME / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "registry.vdf",
)
_LOG_NAMES = ("console_log.txt", "console-linux.txt")

_RUNNING_APPID_RE = re.compile(r'"RunningAppID"\s+"(\d+)"', re.IGNORECASE)
_GAME_ACTION_RE = re.compile(
    r"GameAction\s*\[AppID (?P<appid>\d+), ActionID (?P<action>\d+)\]\s*:\s*(?P<text>.*)"
)
_TASK_RE = re.compile(r"changed task to (?P<task>\w+)")
_ACTION_END_RE = re.compile(r"\b(fail\w*|cancel\w*|abort\w*|error)\b", re.IGNORECASE)
_PROCESS_LINE_RE = re.compile(
    r"(?:Game process (?:added|updated)\s*:\s*AppID (?P<a>\d+)"
    r"|Game update:\s*AppID (?P<b>\d+)"
    r"|>>> Adding process \d+ for game ID (?P<c>\d+))"
)


class _State(enum.Enum):
    """Where the monitored game is in its life cycle."""

    LAUNCHING = "launching"
    RUNNING = "running"
    LINGERING = "lingering"


@dataclass
class _Options:
    """Timeouts and behaviour, from the command line."""

    appid: str | None
    steam_bin: str
    close_launcher: bool
    steam_start_timeout: float = DEFAULT_STEAM_START_TIMEOUT
    launch_quiet_timeout: float = DEFAULT_LAUNCH_QUIET_TIMEOUT
    exit_grace: float = DEFAULT_EXIT_GRACE
    relaunch_grace: float = DEFAULT_RELAUNCH_GRACE


@dataclass
class _LogWatcher:
    """Follows Steam's console log, reading only lines written after start."""

    path: Path | None
    offset: int = 0
    partial: str = ""

    @classmethod
    def at_end(cls) -> _LogWatcher:
        """A watcher on the newest console log, positioned at its end."""
        candidates = [
            root / "logs" / name
            for root in _STEAM_ROOTS
            for name in _LOG_NAMES
            if (root / "logs" / name).is_file()
        ]
        if not candidates:
            _logger.info("no Steam console log found, relying on processes only")
            return cls(path=None)
        path = max(candidates, key=lambda p: p.stat().st_mtime)
        _logger.debug("following %s", path)
        return cls(path=path, offset=path.stat().st_size)

    def new_lines(self) -> list[str]:
        """Complete lines appended since the last call."""
        if self.path is None:
            return []
        try:
            size = self.path.stat().st_size
            if size < self.offset:  # rotated or truncated by a new Steam run
                self.offset, self.partial = 0, ""
            if size == self.offset:
                return []
            with self.path.open("r", encoding="utf-8", errors="replace") as log:
                log.seek(self.offset)
                chunk = log.read()
                self.offset = log.tell()
        except OSError:
            return []
        text = self.partial + chunk
        lines = text.split("\n")
        self.partial = lines.pop()
        return lines


@dataclass
class _LaunchTracker:
    """What the console log says about the launches of one AppId."""

    appid: str
    preparing: bool = False
    process_reported: bool = False
    actions: set[str] = field(default_factory=set)

    def feed(self, lines: list[str]) -> bool:
        """Parse new log lines; True if any of them concerns this AppId."""
        touched = False
        for line in lines:
            action = _GAME_ACTION_RE.search(line)
            if action and action.group("appid") == self.appid:
                touched = True
                self._on_action(action.group("action"), action.group("text"))
                continue
            process = _PROCESS_LINE_RE.search(line)
            if process and self.appid in process.groups():
                touched = True
                self.process_reported = True
        return touched

    def _on_action(self, action_id: str, text: str) -> None:
        if action_id not in self.actions:
            self.actions.add(action_id)
            _logger.info("Steam started launch action %s", action_id)
        task = _TASK_RE.search(text)
        if task:
            name = task.group("task")
            _logger.info("launch task: %s", name)
            self.preparing = name != "Completed"
        elif _ACTION_END_RE.search(text):
            _logger.info("launch action ended: %s", text.strip())
            self.preparing = False
        else:
            self.preparing = True  # waiting for a user response, etc.


def _processes() -> Iterator[tuple[str, list[str]]]:
    """(comm, argv) of every process we are allowed to inspect."""
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"/proc/{entry.name}/cmdline", "rb") as cmdline:
                raw = cmdline.read()
            with open(f"/proc/{entry.name}/comm", "r", encoding="utf-8") as comm:
                name = comm.read().strip()
        except OSError:
            continue
        argv = [arg.decode(errors="replace") for arg in raw.split(b"\0") if arg]
        yield name, argv


def _reaper_alive(appid: str) -> bool:
    """Whether Steam's reaper for this AppId is running."""
    token = f"AppId={appid}"
    return any(
        "SteamLaunch" in argv and token in argv for _name, argv in _processes()
    )


def _shader_cache_busy(appid: str) -> bool:
    """Whether fossilize_replay is processing this game's shader cache."""
    marker = f"/shadercache/{appid}/"
    for name, argv in _processes():
        if not name.startswith("fossilize_repl"):
            continue
        if any(marker in arg for arg in argv):
            return True
    return False


def _steam_running() -> bool:
    """Whether the Steam client is running."""
    return any(name == "steam" for name, _argv in _processes())


def _registry_says_running(appid: str) -> bool:
    """Whether registry.vdf reports this AppId as the running one."""
    for registry in _REGISTRY_FILES:
        try:
            match = _RUNNING_APPID_RE.search(registry.read_text(errors="replace"))
        except OSError:
            continue
        if match:
            return match.group(1) == appid
    return False


def _launch_steam(steam_bin: str, args: list[str]) -> None:
    """Start Steam detached, so neither its output nor its life ties us up."""
    command = [steam_bin, *args]
    _logger.info("running: %s", " ".join(command))
    try:
        subprocess.Popen(  # pylint: disable=consider-using-with
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as err:
        _logger.error("cannot run Steam: %s", err)


def _shutdown_steam(options: _Options) -> None:
    """Shut Steam down if close_game_launcher asked for it."""
    if options.close_launcher:
        _logger.info("closing Steam (close_game_launcher)")
        _launch_steam(options.steam_bin, ["-shutdown"])


def _wait_for_steam(options: _Options, start: float) -> bool:
    deadline = start + options.steam_start_timeout
    while time.monotonic() < deadline:
        if _steam_running():
            return True
        time.sleep(POLL_INTERVAL)
    return False


class _GameWatch:  # pylint: disable=too-few-public-methods
    """The state machine following one launched game."""

    def __init__(self, options: _Options, appid: str) -> None:
        self.options = options
        self.appid = appid
        self.log = _LogWatcher.at_end()
        self.tracker = _LaunchTracker(appid)
        self.state = _State.LAUNCHING
        self.state_since = self.last_activity = time.monotonic()
        self.grace = options.exit_grace
        self.reaper_seen = False

    @property
    def poll_interval(self) -> float:
        """How long to sleep before the next step."""
        if self.state is _State.LINGERING:
            return LINGER_POLL_INTERVAL
        return POLL_INTERVAL

    def _game_alive(self) -> bool:
        """Whether the game runs, by its reaper once one has been seen.

        registry.vdf is only a fallback for setups without a reaper: Steam
        updates it late, so trusting it after the reaper is gone would only
        delay the return to the frontend.
        """
        if _reaper_alive(self.appid):
            self.reaper_seen = True
            return True
        return not self.reaper_seen and _registry_says_running(self.appid)

    def _enter(self, state: _State, now: float) -> None:
        self.state, self.state_since = state, now

    def _step_launching(self, now: float, alive: bool, touched: bool) -> bool:
        """Wait for the game to show up; False to give up."""
        if alive:
            _logger.info("game %s is running", self.appid)
            self.tracker.preparing = False  # whatever Steam logs, it launched
            self._enter(_State.RUNNING, now)
            return True
        if touched or self.tracker.preparing or _shader_cache_busy(self.appid):
            self.last_activity = now
        if now - self.last_activity >= self.options.launch_quiet_timeout:
            _logger.warning("no sign of game %s for %ds, giving up",
                            self.appid, self.options.launch_quiet_timeout)
            return False
        if now - self.state_since >= DEFAULT_LAUNCH_MAX_TIMEOUT:
            _logger.warning("launch of %s took too long, giving up", self.appid)
            return False
        return True

    def _step_running(self, now: float, alive: bool) -> bool:
        """Notice the game going away."""
        if not alive:
            lived = now - self.state_since
            self.grace = (self.options.relaunch_grace if lived < SHORT_RUN
                          else self.options.exit_grace)
            _logger.info("game %s gone after %ds, waiting %ds in case it comes back",
                         self.appid, lived, self.grace)
            self._enter(_State.LINGERING, now)
        return True

    def _step_lingering(self, now: float, alive: bool) -> bool:
        """Wait out the grace period; False once the game is finished."""
        if alive:
            _logger.info("game %s is back", self.appid)
            self.tracker.preparing = False
            self._enter(_State.RUNNING, now)
        elif self.tracker.preparing:
            # A new launch action (Steam or the game restarting it, e.g.
            # after compiling shaders): be patient again.
            _logger.info("Steam is relaunching %s", self.appid)
            self._enter(_State.LAUNCHING, now)
            self.last_activity = now
        elif now - self.state_since >= self.grace:
            _logger.info("game %s finished", self.appid)
            return False
        return True

    def step(self) -> bool:
        """One poll; False when there is nothing left to wait for."""
        now = time.monotonic()
        touched = self.tracker.feed(self.log.new_lines())
        alive = self._game_alive()
        if self.state is _State.LAUNCHING:
            return self._step_launching(now, alive, touched)
        if self.state is _State.RUNNING:
            return self._step_running(now, alive)
        return self._step_lingering(now, alive)


def _watch_game(options: _Options) -> int:
    """Launch options.appid and return once the game is over."""
    assert options.appid is not None
    watch = _GameWatch(options, options.appid)
    _launch_steam(options.steam_bin, ["-silent", "-applaunch", options.appid])
    start = time.monotonic()
    while watch.step():
        if time.monotonic() - start >= DEFAULT_MAX_TOTAL:
            _logger.warning("session time limit reached, giving up")
            break
        time.sleep(watch.poll_interval)
    _shutdown_steam(options)
    return 0


def _watch_big_picture(options: _Options) -> int:
    """Start Big Picture and return once the Steam client exits."""
    _launch_steam(options.steam_bin, ["-bigpicture", "-gamepadui"])
    start = time.monotonic()
    if not _wait_for_steam(options, start):
        _logger.warning("Steam did not start in %ds", options.steam_start_timeout)
        return 0
    _logger.info("Steam is running, waiting for it to exit")
    while time.monotonic() - start < DEFAULT_MAX_TOTAL:
        if not _steam_running():
            _logger.info("Steam exited")
            return 0
        time.sleep(POLL_INTERVAL)
    _logger.warning("session time limit reached, giving up")
    return 0


def _on_terminate(sig: int, _frame: FrameType | None) -> None:
    _logger.info("stopped by signal %d", sig)
    sys.exit(0)


def _parse_arguments(argv: list[str] | None) -> _Options:
    parser = argparse.ArgumentParser(
        prog="python3 -m retrobox.configgen.generators.steam.steam_monitor",
        description="Launch a Steam game and wait until it has really finished.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--appid", help="Steam AppId of the game to launch")
    target.add_argument(
        "--big-picture", action="store_true", help="start Big Picture instead of a game"
    )
    parser.add_argument("--steam-bin", default="steam", help="Steam executable")
    parser.add_argument(
        "--close-launcher", action="store_true", help="shut Steam down after the game"
    )
    parser.add_argument("--launch-quiet-timeout", type=float,
                        default=DEFAULT_LAUNCH_QUIET_TIMEOUT)
    parser.add_argument("--exit-grace", type=float, default=DEFAULT_EXIT_GRACE)
    parser.add_argument("--relaunch-grace", type=float, default=DEFAULT_RELAUNCH_GRACE)
    parser.add_argument("--steam-start-timeout", type=float,
                        default=DEFAULT_STEAM_START_TIMEOUT)
    args = parser.parse_args(argv)
    if args.appid is not None and not args.appid.isdigit():
        parser.error(f"invalid AppId: {args.appid!r}")
    return _Options(
        appid=None if args.big_picture else args.appid,
        steam_bin=args.steam_bin,
        close_launcher=args.close_launcher,
        steam_start_timeout=args.steam_start_timeout,
        launch_quiet_timeout=args.launch_quiet_timeout,
        exit_grace=args.exit_grace,
        relaunch_grace=args.relaunch_grace,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="[steam-monitor] %(message)s",
    )
    signal.signal(signal.SIGTERM, _on_terminate)
    options = _parse_arguments(argv)
    if options.appid is None:
        return _watch_big_picture(options)
    return _watch_game(options)


if __name__ == "__main__":
    sys.exit(main())
