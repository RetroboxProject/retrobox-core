"""The game's control channel: what retrobox-overlay asks of the emulator.

While the game runs, the launcher serves a Unix socket (``CONTROL_SOCKET``,
owner only). Each request is one line, answered with one line::

    pause | resume | do <action> | save_slot <n> | load_slot <n> | discs
    -> ok [<answer>] | error <reason>

``discs`` answers ``ok <disc> <discs> open|closed`` for a game made of
several discs: the channel keeps track of the disc in the drive and of the
tray, since every disc change goes through it (the overlay, and the disc
hotkeys through ``retrobox-control``). Like RetroArch, a disc only changes
with the tray open, and stops at the first and last disc.

Every request is carried out the best way the emulator allows:

1. a command on the emulator's command pipe (``Generator.pipe_commands``:
   RetroArch), which needs no keyboard focus and no timing;
2. else the key chord of the action's hotkey binding, pressed on a virtual
   keyboard the launcher creates when the game starts (so it is known to the
   compositor and the emulator long before it is needed);
3. else the binding's command line.

``pause`` leaves the game paused and ``resume`` leaves it running, whatever
it was before. With a ``status`` pipe command (RetroArch's ``GET_STATUS``,
answered on the emulator's standard output) the channel asks the emulator
first; otherwise it keeps track of the pauses it made itself (the emulators'
pause is a toggle). Save state slots need the pipe: the channel moves the
emulator's current slot to the requested one and remembers where it left it.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from retrobox.configgen.hotkeys import Exec, HotkeyAction, Keys, Native
from retrobox.paths import CONTROL_SOCKET

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    from retrobox.configgen.hotkeys import Binding

_logger = logging.getLogger(__name__)

# The actions the overlay offers from its menu (pause has requests of its own).
MENU_ACTIONS: tuple[HotkeyAction, ...] = (
    HotkeyAction.SAVE_STATE,
    HotkeyAction.LOAD_STATE,
    HotkeyAction.RESET,
    HotkeyAction.MENU,
    HotkeyAction.DISK_EJECT,
    HotkeyAction.DISK_NEXT,
    HotkeyAction.DISK_PREV,
    HotkeyAction.SCREENSHOT,
)
# Pipe commands for slots, besides the actions' own (see Generator.pipe_commands).
SLOT_LOAD = "slot_load"  # with "{slot}" in the command
SLOT_PLUS = "slot_plus"
SLOT_MINUS = "slot_minus"
STATUS = "status"  # answered by a "<command> PAUSED|PLAYING ..." output line
_STATUS_TIMEOUT = 1.0

_HOLD_SECONDS = 0.06  # a chord stays down a few frames
_KEYBOARD_NAME = "retrobox keyboard"
_LAST_KEY = 248  # KEY_MICMUTE: every ordinary key, so udev tags it a keyboard


@dataclass
class Discs:
    """The discs of a playlist game: which one is in the drive, and the tray."""

    count: int
    current: int = 1
    tray_open: bool = False

    @classmethod
    def of_playlist(cls, playlist: Path, saves: Path) -> Discs | None:
        """From an .m3u (one disc per line) and RetroArch's last used disc.

        RetroArch restores the disc it had at the end of the last session from
        ``<saves>/<rom folder>/<name>.ldci`` (``image_index``, from 0).
        """
        if playlist.suffix.lower() != ".m3u":
            return None
        try:
            lines = playlist.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        count = sum(1 for line in lines if line.strip() and not line.startswith("#"))
        if count < 2:
            return None
        current = 1
        for index_file in (saves / playlist.parent.name / f"{playlist.stem}.ldci",
                           saves / f"{playlist.stem}.ldci"):
            with contextlib.suppress(OSError, ValueError, TypeError):
                index = int(json.loads(index_file.read_text(encoding="utf-8"))["image_index"])
                current = min(max(index + 1, 1), count)
                break
        return cls(count=count, current=current)

    def apply(self, action: str) -> None:
        """Follow a disc action the emulator was asked to do."""
        if action == HotkeyAction.DISK_EJECT.value:
            self.tray_open = not self.tray_open
        elif action == HotkeyAction.DISK_NEXT.value and self.tray_open:
            self.current = min(self.current + 1, self.count)
        elif action == HotkeyAction.DISK_PREV.value and self.tray_open:
            self.current = max(self.current - 1, 1)

    def answer(self) -> str:
        """The ``discs`` answer."""
        return f"ok {self.current} {self.count} {'open' if self.tray_open else 'closed'}"


@dataclass
class _Way:
    """How one request is carried out."""

    command: str | None = None
    keys: tuple[str, ...] = ()
    argv: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.command or self.keys or self.argv)


@dataclass
class Control:  # pylint: disable=too-many-instance-attributes
    """The emulator of the running game, as the control channel drives it."""

    bindings: Mapping[HotkeyAction, Binding]
    pipe: Path | None = None
    pipe_commands: Mapping[str, str] = field(default_factory=dict)
    slot: int = 0
    discs: Discs | None = None
    paused: bool = False
    _keyboard: object | None = None
    _status: str | None = None
    _status_ready: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        if self.pipe is None:
            self.pipe_commands = {}
        if any(self._way(name).keys for name in self._names()):
            self._keyboard = _create_keyboard()

    @staticmethod
    def _names() -> list[str]:
        return [HotkeyAction.PAUSE.value] + [action.value for action in MENU_ACTIONS]

    def _way(self, name: str) -> _Way:
        if command := self.pipe_commands.get(name):
            return _Way(command=command)
        binding = self.bindings.get(HotkeyAction(name))
        if isinstance(binding, Keys):
            return _Way(keys=binding.codes)
        if isinstance(binding, Native):
            return _Way(keys=binding.keys)
        if isinstance(binding, Exec):
            return _Way(argv=binding.argv)
        return _Way()

    def _usable(self, way: _Way) -> bool:
        return bool(way.command or way.argv or (way.keys and self._keyboard is not None))

    def can_pause(self) -> bool:
        """Whether the game can be paused."""
        return self._usable(self._way(HotkeyAction.PAUSE.value))

    def actions(self) -> list[str]:
        """The menu actions the emulator can do."""
        return [action.value for action in MENU_ACTIONS if self._usable(self._way(action.value))]

    def has_slots(self) -> bool:
        """Whether save states can be saved and loaded by slot."""
        return all(
            name in self.pipe_commands
            for name in (SLOT_LOAD, SLOT_PLUS, SLOT_MINUS, HotkeyAction.SAVE_STATE.value)
        )

    def needs_focus(self) -> bool:
        """Whether some request presses keys, which only reach a focused game."""
        names = self._names()
        return self._keyboard is not None and any(self._way(name).keys for name in names)

    def describe(self) -> dict[str, object]:
        """What session.json tells the overlay about the channel."""
        return {
            "socket": str(CONTROL_SOCKET),
            "pause": self.can_pause(),
            "actions": self.actions(),
            "slots": self.has_slots(),
            "discs": self.discs is not None,
            "focus": self.needs_focus(),
        }

    def handle(self, request: str) -> str:
        """Carry out one request; the answer line."""
        verb, _, argument = request.strip().partition(" ")
        handlers = {
            "pause": lambda: self._toggle_pause(pause=True),
            "resume": lambda: self._toggle_pause(pause=False),
            "do": lambda: self._do(argument),
            "save_slot": lambda: self._slot(verb, int(argument)),
            "load_slot": lambda: self._slot(verb, int(argument)),
            "discs": self._discs,
        }
        handler = handlers.get(verb)
        if handler is None:
            return f"error unknown request {verb!r}"
        try:
            return handler()
        except (ValueError, OSError) as err:
            return f"error {err}"

    def _discs(self) -> str:
        return self.discs.answer() if self.discs else "error not a multi-disc game"

    def _toggle_pause(self, pause: bool) -> str:
        status = self._query_status()
        if status is not None:
            self.paused = status == "PAUSED"
        if self.paused == pause:
            return "ok"
        result = self._run(self._way(HotkeyAction.PAUSE.value))
        if result == "ok":
            self.paused = pause
        return result

    def _query_status(self) -> str | None:
        """PAUSED or PLAYING as the emulator says; None when it cannot say."""
        command = self.pipe_commands.get(STATUS)
        if not command:
            return None
        self._status = None
        self._status_ready.clear()
        if self._send([command]) != "ok" or not self._status_ready.wait(_STATUS_TIMEOUT):
            # not worth waiting every time: keep track of the pauses instead
            _logger.warning("no answer to %s: keeping track of the pauses", command)
            self.pipe_commands = {
                name: value for name, value in self.pipe_commands.items() if name != STATUS
            }
            return None
        return self._status

    def on_output(self, line: str) -> None:
        """A line of the emulator's standard output: the answer to ``status``?"""
        command = self.pipe_commands.get(STATUS)
        if command and line.startswith(f"{command} "):
            self._status = line.split()[1]
            self._status_ready.set()

    def _do(self, name: str) -> str:
        if name not in self.actions():
            return f"error {name!r} is not available"
        result = self._run(self._way(name))
        if result == "ok" and self.discs is not None:
            self.discs.apply(name)
        return result

    def _slot(self, verb: str, slot: int) -> str:
        if not self.has_slots():
            return "error no save state slots"
        if verb == "load_slot":
            return self._send([self.pipe_commands[SLOT_LOAD].format(slot=slot)])
        step = self.pipe_commands[SLOT_PLUS if slot > self.slot else SLOT_MINUS]
        commands = [step] * abs(slot - self.slot)
        commands.append(self.pipe_commands[HotkeyAction.SAVE_STATE.value])
        result = self._send(commands)
        if result == "ok":
            self.slot = slot
        return result

    def _run(self, way: _Way) -> str:
        if way.command:
            return self._send([way.command])
        if way.keys and self._keyboard is not None:
            _press(self._keyboard, way.keys)
            return "ok"
        if way.argv:
            subprocess.Popen(  # pylint: disable=consider-using-with
                way.argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return "ok"
        return "error not available"

    def _send(self, commands: list[str]) -> str:
        if self.pipe is None:
            return "error no command pipe"
        fd = os.open(self.pipe, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, "".join(f"{command}\n" for command in commands).encode())
        finally:
            os.close(fd)
        return "ok"

    def close(self) -> None:
        """Remove the virtual keyboard."""
        if self._keyboard is not None:
            self._keyboard.close()  # type: ignore[attr-defined]
            self._keyboard = None


def _create_keyboard() -> object | None:
    """The virtual keyboard, or None (and a warning) without /dev/uinput."""
    try:
        # pylint: disable-next=import-outside-toplevel
        from evdev import UInput, ecodes

        return UInput(
            {ecodes.EV_KEY: list(range(1, _LAST_KEY + 1))},
            name=_KEYBOARD_NAME,
        )
    except (ImportError, OSError) as err:
        _logger.warning("no virtual keyboard for the control channel: %s", err)
        return None


def _press(keyboard: object, keys: tuple[str, ...]) -> None:
    """Press a chord: modifiers first, released in reverse order."""
    # pylint: disable-next=import-outside-toplevel
    from evdev import ecodes

    codes = [ecodes.ecodes[name] for name in keys if name in ecodes.ecodes]
    for code in codes:
        keyboard.write(ecodes.EV_KEY, code, 1)  # type: ignore[attr-defined]
    keyboard.syn()  # type: ignore[attr-defined]
    time.sleep(_HOLD_SECONDS)
    for code in reversed(codes):
        keyboard.write(ecodes.EV_KEY, code, 0)  # type: ignore[attr-defined]
    keyboard.syn()  # type: ignore[attr-defined]


class _Handler(socketserver.StreamRequestHandler):
    """One client: requests and answers, a line each."""

    server: _Server

    def handle(self) -> None:
        for raw in self.rfile:
            request = raw.decode(errors="replace").strip()
            if not request:
                continue
            answer = self.server.control.handle(request)
            _logger.info("control: %s -> %s", request, answer)
            self.wfile.write(f"{answer}\n".encode())


class _Server(socketserver.UnixStreamServer):
    """Serves one client at a time: requests are short and must not overlap."""

    def __init__(self, path: Path, control: Control):
        self.control = control
        super().__init__(str(path), _Handler)


def send_request(line: str, path: Path = CONTROL_SOCKET) -> str:
    """Send one request to the running game's channel; its answer."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(path))
        client.sendall(f"{line}\n".encode())
        return client.makefile("r", encoding="utf-8").readline().strip()


def main(argv: list[str] | None = None) -> int:
    """``retrobox-control <request...>``: one request, for hotkeys and scripts."""
    words = sys.argv[1:] if argv is None else argv
    if not words:
        print("usage: retrobox-control pause|resume|do <action>|save_slot <n>|"
              "load_slot <n>|discs", file=sys.stderr)
        return 2
    try:
        answer = send_request(" ".join(words))
    except OSError as err:
        print(f"retrobox-control: no game running ({err})", file=sys.stderr)
        return 1
    print(answer)
    return 0 if answer.startswith("ok") else 1


@contextlib.contextmanager
def serve(control: Control, path: Path = CONTROL_SOCKET) -> Iterator[Control]:
    """Serve the control channel while the block runs."""
    server = None
    try:
        path.unlink(missing_ok=True)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        old_umask = os.umask(0o077)
        try:
            server = _Server(path, control)
        finally:
            os.umask(old_umask)
        threading.Thread(target=server.serve_forever, name="control", daemon=True).start()
    except OSError as err:
        _logger.warning("no control channel at %s: %s", path, err)
    try:
        yield control
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        path.unlink(missing_ok=True)
        control.close()


if __name__ == "__main__":
    sys.exit(main())
