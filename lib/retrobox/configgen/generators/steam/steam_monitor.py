"""Launch a Steam game and block until it has really finished.

Run as ``python3 -m retrobox.configgen.generators.steam.steam_monitor``. The
launcher waits for this process, so EmulationStation stays out of the way
for exactly as long as the game is alive.

Steam hands a launch over to its client and returns at once, so the game has
to be watched from outside. Before the game process exists Steam may spend a
long time preparing it (Vulkan shader pre-caching, an update, cloud sync, the
first run of a Proton prefix or of the Steam Linux Runtime), and some games
exit and are started again by Steam.

Like Playnite, the monitor never gives up on a launch because it takes long:
returning to the frontend while the game is still coming up is worse than
waiting. It only stops waiting on a clear sign that the game is not coming:

* the Steam client exits (or never starts);
* Steam logs that the launch action failed or was cancelled;
* Steam logs that the game's process ended before it was ever seen;
* Alt+F4 is pressed on any keyboard, gamepadly's virtual one included (the
  Hotkey+Start exit of Retrobox), while the game hasn't shown up yet.

The game counts as alive while any of these is there:

* the ``reaper SteamLaunch AppId=<id>`` process, which Steam keeps alive for
  as long as any process of the game runs;
* a process whose environment carries ``SteamAppId``/``SteamGameId`` = the
  AppId (the whole game tree: Proton, Wine, the game itself);
* a process running from the game's install folder
  (``steamapps/common/<installdir>``), as Playnite tracks Steam games;
* ``RunningAppID`` in ``registry.vdf``, only for setups where none of the
  above ever shows up.

Once the game disappears the monitor waits a short grace period in case it
comes back (a relaunch). Everything it sees goes to ``steam-monitor.log`` in
Retrobox's log directory.
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
    from types import FrameType

_logger = logging.getLogger("steam-monitor")

POLL_INTERVAL = 1.0
"""Seconds between two checks."""

LINGER_POLL_INTERVAL = 0.5
"""Seconds between two checks once the game is gone, to return quickly."""

STATUS_EVERY = 30.0
"""Seconds between two status lines in the log while waiting for a launch."""

DEFAULT_STEAM_START_TIMEOUT = 300
"""Seconds to wait for the Steam client itself to appear."""

LAUNCH_END_GRACE = 15
"""Seconds the game may still take to appear once Steam gave up on it."""

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
_INSTALLDIR_RE = re.compile(r'"installdir"\s+"([^"]+)"', re.IGNORECASE)
_GAME_ACTION_RE = re.compile(
    r"GameAction\s*\[AppID (?P<appid>\d+), ActionID (?P<action>\d+)\]\s*:\s*(?P<text>.*)"
)
_TASK_RE = re.compile(r"changed task to (?P<task>\w+)")
_ACTION_END_RE = re.compile(r"\b(fail\w*|cancel\w*|abort\w*|error)\b", re.IGNORECASE)
_PROCESS_ADDED_RE = re.compile(
    r"(?:Game process (?:added|updated)\s*:\s*AppID (?P<a>\d+)"
    r"|Game update:\s*AppID (?P<b>\d+)"
    r"|>>> Adding process \d+ for game ID (?P<c>\d+))"
)
_PROCESS_REMOVED_RE = re.compile(
    r"(?:Game process removed:\s*AppID (?P<a>\d+)|Game removed:\s*AppID (?P<b>\d+))"
)
_STEAM_NAMES = frozenset({"steam", "steam.sh"})  # client, and its bootstrap script
_FOSSILIZE_PREFIX = "fossilize_repl"  # comm is cut to 15 characters

_EV_KEY = 1
_KEY_LEFTALT = 56
_KEY_RIGHTALT = 100
_KEY_F4 = 62


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
    exit_grace: float = DEFAULT_EXIT_GRACE
    relaunch_grace: float = DEFAULT_RELAUNCH_GRACE


# ---------------------------------------------------------------------------
# The game's install folder
# ---------------------------------------------------------------------------


def _libraries() -> list[Path]:
    """Steam libraries, found the same way the ES sync finds them."""
    try:
        # pylint: disable-next=import-outside-toplevel
        from retrobox.startup.frontend_conf.pcgames_utils import _steam_libraries
        return _steam_libraries()
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.debug("Retrobox's Steam library lookup unavailable", exc_info=True)
        return [root for root in _STEAM_ROOTS if (root / "steamapps").is_dir()]


def _install_dir(appid: str) -> Path | None:
    """steamapps/common/<installdir> of the game, from its appmanifest."""
    for library in _libraries():
        manifest = library / "steamapps" / f"appmanifest_{appid}.acf"
        try:
            match = _INSTALLDIR_RE.search(manifest.read_text(errors="replace"))
        except OSError:
            continue
        if match:
            folder = library / "steamapps" / "common" / match.group(1)
            if folder.is_dir():
                return folder
    return None


def _path_forms(folder: Path | None) -> tuple[str, ...]:
    """Lower-case spellings of a folder in Unix and Wine (Z:) command lines.

    Both the path as Steam knows it and the resolved one, since libraries are
    often reached through symlinks (~/.steam/steam). Command lines are
    compared with "/" separators, so Z:\\... and Z:/... both match.
    """
    if folder is None:
        return ()
    forms: list[str] = []
    for path in dict.fromkeys((str(folder), str(folder.resolve()))):
        unix = path.lower().rstrip("/") + "/"
        forms += [unix, "z:" + unix]
    return tuple(forms)


# ---------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Snapshot:
    """What the process table says at one moment."""

    steam: bool = False
    reaper: bool = False
    game_processes: int = 0
    folder_processes: int = 0
    fossilize: bool = False

    @property
    def game_seen(self) -> bool:
        """Whether any game-specific signal is present."""
        return self.reaper or bool(self.game_processes) or bool(self.folder_processes)

    def describe(self) -> str:
        """One-line summary for the log."""
        return (f"steam={self.steam} reaper={self.reaper} "
                f"game_processes={self.game_processes} "
                f"folder_processes={self.folder_processes} fossilize={self.fossilize}")


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as source:
            return source.read()
    except OSError:
        return b""


def _in_folder(raw_argv: bytes, folder_forms: tuple[str, ...]) -> bool:
    """Whether a command line runs something from the game folder.

    Only the command line, like Playnite only looks at the executable: a
    working directory would also catch a shell or a file manager there.
    """
    if not folder_forms:
        return False
    argv = raw_argv.decode(errors="replace").lower().replace("\\", "/")
    return any(form in argv for form in folder_forms)


@dataclass
class _Scanner:
    """Takes snapshots of the processes related to one AppId."""

    appid: str | None
    folder_forms: tuple[str, ...] = ()
    env_tokens: set[bytes] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.appid is None:
            return
        self.env_tokens = {f"SteamAppId={self.appid}".encode(),
                           f"SteamGameId={self.appid}".encode()}
        own = _read_bytes(f"/proc/{os.getpid()}/environ").split(b"\0")
        if self.env_tokens.intersection(own):
            self.env_tokens = set()  # started from a Steam game: useless here

    def scan(self) -> _Snapshot:
        """One pass over /proc looking for Steam, the game and shader work."""
        own_pid = str(os.getpid())
        reaper_token = f"AppId={self.appid}"
        steam = reaper = fossilize = False
        game_processes = folder_processes = 0

        for entry in os.scandir("/proc"):
            pid = entry.name
            if not pid.isdigit() or pid == own_pid:
                continue
            raw_argv = _read_bytes(f"/proc/{pid}/cmdline")
            if not raw_argv:  # kernel thread, zombie or already gone
                continue
            name = _read_bytes(f"/proc/{pid}/comm").decode(errors="replace").strip()
            if name in _STEAM_NAMES:
                steam = True
                continue
            if name.startswith(_FOSSILIZE_PREFIX):
                fossilize = True
                continue  # Steam also runs it after a game, in the background
            if self.appid is None:
                continue
            argv = [arg.decode(errors="replace") for arg in raw_argv.split(b"\0") if arg]
            if "SteamLaunch" in argv and reaper_token in argv:
                reaper = True
                continue
            environ = _read_bytes(f"/proc/{pid}/environ")
            if environ and self.env_tokens.intersection(environ.split(b"\0")):
                game_processes += 1
            elif _in_folder(raw_argv, self.folder_forms):
                folder_processes += 1

        return _Snapshot(steam=steam, reaper=reaper, game_processes=game_processes,
                         folder_processes=folder_processes, fossilize=fossilize)


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


# ---------------------------------------------------------------------------
# Alt+F4: the way out while the game hasn't shown up
# ---------------------------------------------------------------------------


@dataclass
class _ExitKeyWatcher:
    """Notices Alt+F4 on any keyboard, without grabbing it from anyone.

    gamepadly turns Hotkey+Start into Alt+F4 on a virtual keyboard, which is
    just one more evdev device here. Needs the "input" group, like the rest
    of Retrobox's keyboard handling; without it the watcher does nothing.
    """

    devices: dict[str, object] = field(default_factory=dict)
    alt_down: set[str] = field(default_factory=set)
    available: bool = True

    def _refresh(self, evdev) -> None:
        for path in evdev.list_devices():
            if path in self.devices:
                continue
            try:
                device = evdev.InputDevice(path)
            except OSError:
                continue
            keys = device.capabilities().get(_EV_KEY, [])
            if _KEY_F4 in keys:
                self.devices[path] = device
            else:
                device.close()

    def pressed(self) -> bool:
        """Whether Alt+F4 was pressed since the last call."""
        if not self.available:
            return False
        try:
            import evdev  # pylint: disable=import-outside-toplevel
        except ImportError:
            _logger.info("python-evdev missing: Alt+F4 can't cancel a launch")
            self.available = False
            return False
        self._refresh(evdev)
        hit = False
        for path, device in list(self.devices.items()):
            try:
                for event in device.read():  # type: ignore[attr-defined]
                    hit |= self._on_event(path, event)
            except BlockingIOError:
                continue
            except OSError:  # unplugged
                self.devices.pop(path, None)
                self.alt_down.discard(path)
        return hit

    def _on_event(self, path: str, event) -> bool:
        if event.type != _EV_KEY:
            return False
        if event.code in (_KEY_LEFTALT, _KEY_RIGHTALT):
            if event.value:
                self.alt_down.add(path)
            else:
                self.alt_down.discard(path)
            return False
        return event.code == _KEY_F4 and event.value == 1 and path in self.alt_down

    def close(self) -> None:
        """Release the devices."""
        for device in self.devices.values():
            try:
                device.close()  # type: ignore[attr-defined]
            except OSError:
                pass
        self.devices.clear()


# ---------------------------------------------------------------------------
# Steam's console logs
# ---------------------------------------------------------------------------


@dataclass
class _LogFile:
    """Read position in one log file, reset when Steam rotates it."""

    path: Path
    inode: int = -1
    offset: int = 0
    partial: str = ""

    def skip_to_end(self) -> None:
        """Ignore what was written before the monitor started."""
        try:
            stat = self.path.stat()
        except OSError:
            return
        self.inode, self.offset = stat.st_ino, stat.st_size

    def new_lines(self) -> list[str]:
        """Complete lines appended since the last call."""
        try:
            stat = self.path.stat()
        except OSError:
            return []
        if stat.st_ino != self.inode or stat.st_size < self.offset:
            # Rotated (Steam starts a new file on every run) or truncated.
            _logger.debug("reading %s from the start", self.path)
            self.inode, self.offset, self.partial = stat.st_ino, 0, ""
        if stat.st_size == self.offset:
            return []
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as log:
                log.seek(self.offset)
                chunk = log.read()
                self.offset = log.tell()
        except OSError:
            return []
        lines = (self.partial + chunk).split("\n")
        self.partial = lines.pop()
        return lines


@dataclass
class _LogWatcher:
    """Follows every Steam console log there is, including ones made later."""

    files: dict[Path, _LogFile] = field(default_factory=dict)

    @staticmethod
    def _candidates() -> set[Path]:
        found: set[Path] = set()
        for root in _STEAM_ROOTS:
            for name in _LOG_NAMES:
                path = root / "logs" / name
                if path.is_file():
                    found.add(path.resolve())  # ~/.steam/steam is a symlink
        return found

    def start(self) -> None:
        """Pick up the existing logs, positioned at their end."""
        for path in self._candidates():
            self.files[path] = log = _LogFile(path)
            log.skip_to_end()
        _logger.info("following Steam logs: %s",
                     ", ".join(str(p) for p in self.files) or "none yet")

    def new_lines(self) -> list[str]:
        """New lines from every log, noticing logs created meanwhile."""
        for path in self._candidates() - self.files.keys():
            _logger.info("following new Steam log: %s", path)
            self.files[path] = _LogFile(path)  # new file: read it all
        lines: list[str] = []
        for log in self.files.values():
            lines += log.new_lines()
        return lines


@dataclass
class _LaunchTracker:
    """What the console log says about the launches of one AppId."""

    appid: str
    preparing: bool = False
    gave_up: bool = False
    process_removed: bool = False
    actions: set[str] = field(default_factory=set)

    def feed(self, lines: list[str]) -> None:
        """Parse new log lines about this AppId."""
        for line in lines:
            action = _GAME_ACTION_RE.search(line)
            if action and action.group("appid") == self.appid:
                self._on_action(action.group("action"), action.group("text"))
                continue
            added = _PROCESS_ADDED_RE.search(line)
            if added and self.appid in added.groups():
                _logger.info("log: %s", line.strip())
                continue
            removed = _PROCESS_REMOVED_RE.search(line)
            if removed and self.appid in removed.groups():
                _logger.info("log: %s", line.strip())
                self.process_removed = True

    def _on_action(self, action_id: str, text: str) -> None:
        if action_id not in self.actions:
            self.actions.add(action_id)
            _logger.info("Steam started launch action %s", action_id)
            self.gave_up = self.process_removed = False
        task = _TASK_RE.search(text)
        if task:
            name = task.group("task")
            _logger.info("launch task: %s", name)
            self.preparing = name != "Completed"
        elif _ACTION_END_RE.search(text):
            _logger.info("launch action ended: %s", text.strip())
            self.preparing = False
            self.gave_up = True
        else:
            self.preparing = True  # waiting for a user response, etc.


# ---------------------------------------------------------------------------
# Steam client
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Watching a game
# ---------------------------------------------------------------------------


class _GameWatch:  # pylint: disable=too-many-instance-attributes
    """The state machine following one launched game."""

    def __init__(self, options: _Options, appid: str) -> None:
        self.options = options
        self.appid = appid
        self.log = _LogWatcher()
        self.tracker = _LaunchTracker(appid)
        self.exit_keys = _ExitKeyWatcher()
        self.scanner = _Scanner(appid)
        self.state = _State.LAUNCHING
        self.started = time.monotonic()
        self.state_since = self.last_status = self.started
        self.doubt_since: float | None = None  # when the launch started to look dead
        self.steam_seen = False
        self.grace = options.exit_grace
        self.ever_seen = False
        self.snapshot = _Snapshot()

    @property
    def poll_interval(self) -> float:
        """How long to sleep before the next step."""
        if self.state is _State.LINGERING:
            return LINGER_POLL_INTERVAL
        return POLL_INTERVAL

    def start(self) -> None:
        """Find the game's folder and the logs, then ask Steam for the game."""
        folder = _install_dir(self.appid)
        _logger.info("install folder: %s", folder or "not found")
        self.scanner.folder_forms = _path_forms(folder)
        self.log.start()
        _launch_steam(self.options.steam_bin, ["-silent", "-applaunch", self.appid])

    def close(self) -> None:
        """Release what the watch holds."""
        self.exit_keys.close()

    def _alive(self, snapshot: _Snapshot) -> bool:
        """Whether the game runs.

        registry.vdf is only a fallback for setups where no game-specific
        process ever shows up: Steam updates it late, so trusting it
        afterwards would only delay the return to the frontend.
        """
        if snapshot.game_seen:
            self.ever_seen = True
            return True
        return not self.ever_seen and _registry_says_running(self.appid)

    def _enter(self, state: _State, now: float) -> None:
        _logger.info("state: %s -> %s", self.state.value, state.value)
        self.state, self.state_since = state, now
        self.doubt_since = None

    def _launch_doubt(self, now: float) -> str:
        """Why the game is believed not to be coming ("" while it may come)."""
        snapshot = self.snapshot
        if snapshot.steam:
            self.steam_seen = True
        elif not self.steam_seen and now - self.started >= self.options.steam_start_timeout:
            return f"Steam did not start in {self.options.steam_start_timeout:.0f}s"
        elif self.steam_seen:
            return "Steam exited"
        if self.tracker.gave_up:
            return "Steam ended the launch action"
        if self.tracker.process_removed:
            return "Steam reports the game's process gone"
        return ""

    def _step_launching(self, now: float, alive: bool) -> bool:
        """Wait for the game to show up, with no time limit; False to give up."""
        if alive:
            self.tracker.preparing = self.tracker.gave_up = False
            self._enter(_State.RUNNING, now)
            return True
        if self.exit_keys.pressed():
            _logger.warning("Alt+F4 pressed before game %s showed up: giving up", self.appid)
            return False
        if now - self.last_status >= STATUS_EVERY:
            self.last_status = now
            _logger.info("still launching (%ds; %s)", now - self.state_since,
                         self.snapshot.describe())
        doubt = self._launch_doubt(now)
        if not doubt:
            self.doubt_since = None
            return True
        if self.doubt_since is None:
            _logger.info("%s; waiting %ds in case the game still comes",
                         doubt, LAUNCH_END_GRACE)
            self.doubt_since = now
        if now - self.doubt_since >= LAUNCH_END_GRACE:
            _logger.warning("%s: giving up on game %s", doubt, self.appid)
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
            self.tracker.preparing = False
            self._enter(_State.RUNNING, now)
        elif self.tracker.preparing:
            # A new launch action (Steam relaunching the game, e.g. after
            # compiling shaders): wait for it like for the first one.
            _logger.info("Steam is relaunching %s", self.appid)
            self._enter(_State.LAUNCHING, now)
        elif now - self.state_since >= self.grace:
            _logger.info("game %s finished", self.appid)
            return False
        return True

    def step(self) -> bool:
        """One poll; False when there is nothing left to wait for."""
        now = time.monotonic()
        self.tracker.feed(self.log.new_lines())
        snapshot = self.scanner.scan()
        if snapshot != self.snapshot:
            _logger.debug("processes: %s", snapshot.describe())
        self.snapshot = snapshot
        alive = self._alive(snapshot)
        if self.state is _State.LAUNCHING:
            return self._step_launching(now, alive)
        if self.state is _State.RUNNING:
            return self._step_running(now, alive)
        return self._step_lingering(now, alive)


def _watch_game(options: _Options) -> int:
    """Launch options.appid and return once the game is over."""
    assert options.appid is not None
    watch = _GameWatch(options, options.appid)
    watch.start()
    try:
        while True:
            try:
                if not watch.step():
                    break
            except Exception:  # pylint: disable=broad-exception-caught
                # A bug here must never send the user back to the frontend
                # while the game is still starting: log it and keep watching.
                _logger.exception("error while watching the game")
            if time.monotonic() - watch.started >= DEFAULT_MAX_TOTAL:
                _logger.warning("session time limit reached, giving up")
                break
            time.sleep(watch.poll_interval)
    finally:
        watch.close()
    _shutdown_steam(options)
    return 0


def _watch_big_picture(options: _Options) -> int:
    """Start Big Picture and return once the Steam client exits."""
    scanner = _Scanner(None)
    _launch_steam(options.steam_bin, ["-bigpicture", "-gamepadui"])
    start = time.monotonic()
    while not scanner.scan().steam:
        if time.monotonic() - start >= options.steam_start_timeout:
            _logger.warning("Steam did not start in %ds", options.steam_start_timeout)
            return 0
        time.sleep(POLL_INTERVAL)
    _logger.info("Steam is running, waiting for it to exit")
    while time.monotonic() - start < DEFAULT_MAX_TOTAL:
        if not scanner.scan().steam:
            _logger.info("Steam exited")
            return 0
        time.sleep(POLL_INTERVAL)
    _logger.warning("session time limit reached, giving up")
    return 0


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _on_terminate(sig: int, _frame: FrameType | None) -> None:
    _logger.info("stopped by signal %d", sig)
    sys.exit(0)


def _setup_logging(log_file: Path | None) -> None:
    """Log to stdout (for the launcher) and to a file kept after the game."""
    formatter = logging.Formatter("%(asctime)s [steam-monitor] %(levelname)s %(message)s")
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    handlers: list[logging.Handler] = [console]
    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_file, mode="w", encoding="utf-8"))
        except OSError:
            pass
    for handler in handlers:
        handler.setFormatter(formatter)
        _logger.addHandler(handler)
    _logger.setLevel(logging.DEBUG)


def _default_log_file() -> Path | None:
    try:
        from retrobox.paths import LOGS  # pylint: disable=import-outside-toplevel
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    return LOGS / "steam-monitor.log"


def _parse_arguments(argv: list[str] | None) -> tuple[_Options, Path | None]:
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
    parser.add_argument("--exit-grace", type=float, default=DEFAULT_EXIT_GRACE)
    parser.add_argument("--relaunch-grace", type=float, default=DEFAULT_RELAUNCH_GRACE)
    parser.add_argument("--steam-start-timeout", type=float,
                        default=DEFAULT_STEAM_START_TIMEOUT)
    parser.add_argument("--log-file", type=Path, help="where to keep the log")
    args = parser.parse_args(argv)
    if args.appid is not None and not args.appid.isdigit():
        parser.error(f"invalid AppId: {args.appid!r}")
    options = _Options(
        appid=None if args.big_picture else args.appid,
        steam_bin=args.steam_bin,
        close_launcher=args.close_launcher,
        steam_start_timeout=args.steam_start_timeout,
        exit_grace=args.exit_grace,
        relaunch_grace=args.relaunch_grace,
    )
    return options, args.log_file or _default_log_file()


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    options, log_file = _parse_arguments(argv)
    _setup_logging(log_file)
    signal.signal(signal.SIGTERM, _on_terminate)
    _logger.info("monitor started for %s", options.appid or "Big Picture")
    if options.appid is None:
        return _watch_big_picture(options)
    return _watch_game(options)


if __name__ == "__main__":
    sys.exit(main())
